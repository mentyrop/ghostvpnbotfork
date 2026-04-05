"""Сервис для работы с Robokassa (форма оплаты и проверка Result URL).

Документация:
- Интерфейс оплаты: https://docs.robokassa.ru/ru/pay-interface
- Уведомления: https://docs.robokassa.ru/ru/notifications-and-redirects
- Фискализация (чеки): https://docs.robokassa.ru/ru/fiscalization
- OpStateExt: https://docs.robokassa.ru/ru/xml-interfaces.html
"""

from __future__ import annotations

import hashlib
import json
import xml.etree.ElementTree as ET
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Iterable
from urllib.parse import quote, urlencode

import httpx
import structlog

from app.config import settings


logger = structlog.get_logger(__name__)

# Базовый URL (тест через параметр IsTest=1)
ROBOKASSA_BASE_URL = 'https://auth.robokassa.ru/Merchant/Index.aspx'
OPSTATE_EXT_URL = 'https://auth.robokassa.ru/Merchant/WebService/Service.asmx/OpStateExt'


def _xml_local(tag: str) -> str:
    return tag.split('}', 1)[-1] if '}' in tag else tag


@dataclass(frozen=True, slots=True)
class OpStateExtResult:
    """Ответ OpStateExt (упрощённо)."""

    result_code: int
    state_code: int | None
    out_sum: str | None

class RobokassaService:
    """Формирование ссылки на оплату и проверка подписи Result URL."""

    def __init__(self):
        self._login: str | None = None
        self._password1: str | None = None
        self._password2: str | None = None

    @property
    def login(self) -> str:
        if self._login is None:
            self._login = settings.ROBOKASSA_MERCHANT_LOGIN or ''
        return self._login

    @property
    def password1(self) -> str:
        if self._password1 is None:
            self._password1 = settings.ROBOKASSA_PASSWORD_1 or ''
        return self._password1

    @property
    def password2(self) -> str:
        if self._password2 is None:
            self._password2 = settings.ROBOKASSA_PASSWORD_2 or ''
        return self._password2

    def _build_receipt_json(self, out_sum: float, item_name: str) -> str:
        """
        Формирует JSON чека для параметра Receipt (ФЗ-54).
        Документация: https://docs.robokassa.ru/ru/fiscalization
        """
        name = (item_name or 'Пополнение баланса')[:128]
        sno = (settings.ROBOKASSA_RECEIPT_SNO or '').strip()
        tax = (settings.ROBOKASSA_RECEIPT_TAX or 'none').strip()
        payment_method = (settings.ROBOKASSA_RECEIPT_PAYMENT_METHOD or 'full_payment').strip()
        payment_object = (settings.ROBOKASSA_RECEIPT_PAYMENT_OBJECT or 'service').strip()
        item = {
            'name': name,
            'quantity': 1,
            'sum': round(out_sum, 2),
            'payment_method': payment_method,
            'payment_object': payment_object,
            'tax': tax,
        }
        receipt: dict = {'items': [item]}
        if sno:
            receipt['sno'] = sno
        # Минимизированный JSON без пробелов (требование Robokassa для подписи)
        return json.dumps(receipt, ensure_ascii=False, separators=(',', ':'))

    def build_signature_for_request(
        self,
        out_sum: float,
        inv_id: int,
        receipt_json: str | None = None,
    ) -> str:
        """
        Подпись для формы оплаты.
        Без чека: MerchantLogin:OutSum:InvId:Password1
        С чеком: MerchantLogin:OutSum:InvId:Receipt:Password1 (Receipt — сырой JSON, не URL-encoded).
        """
        out_str = f'{out_sum:.2f}'
        if receipt_json:
            sign_str = f'{self.login}:{out_str}:{inv_id}:{receipt_json}:{self.password1}'
        else:
            sign_str = f'{self.login}:{out_str}:{inv_id}:{self.password1}'
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()

    @staticmethod
    def extract_shp_sorted(pairs: Iterable[tuple[str, str]]) -> list[tuple[str, str]]:
        """Параметры Shp_* для строки подписи Result URL (сортировка по имени ключа)."""
        shp: list[tuple[str, str]] = []
        for raw_k, raw_v in pairs:
            k = (raw_k or '').strip()
            if k.lower().startswith('shp_'):
                shp.append((k, str(raw_v).strip()))
        shp.sort(key=lambda item: item[0].lower())
        return shp

    def verify_result_signature(
        self,
        out_sum: str,
        inv_id: str,
        signature_value: str,
        shp_sorted: list[tuple[str, str]] | None = None,
    ) -> bool:
        """
        Проверка подписи уведомления Result URL.
        Без Shp_: OutSum:InvId:Password2
        С Shp_: OutSum:InvId:Password2:Shp_key=value (сортировка по ключу).
        В ЛК может быть выбран MD5 или SHA256 — проверяем оба.
        OutSum в строке подписи — как в запросе (в т.ч. 6 знаков после точки в бою; не меняем запятую).
        """
        out_for_sign = (out_sum or '').strip()
        inv_norm = (inv_id or '').strip()
        if shp_sorted:
            shp_part = ':'.join(f'{k}={v}' for k, v in shp_sorted)
            sign_str = f'{out_for_sign}:{inv_norm}:{self.password2}:{shp_part}'
        else:
            sign_str = f'{out_for_sign}:{inv_norm}:{self.password2}'
        payload = sign_str.encode('utf-8')
        received = (signature_value or '').strip().lower()
        md5_hex = hashlib.md5(payload).hexdigest().lower()
        sha256_hex = hashlib.sha256(payload).hexdigest().lower()
        return received in {md5_hex, sha256_hex}

    def build_op_state_ext_signature(self, inv_id: int) -> str:
        """MD5(MerchantLogin:InvoiceID:Password2) для OpStateExt."""
        sign_str = f'{self.login}:{inv_id}:{self.password2}'
        return hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()

    def parse_op_state_ext_xml(self, xml_text: str) -> OpStateExtResult | None:
        try:
            root = ET.fromstring(xml_text)
        except ET.ParseError as e:
            logger.warning('Robokassa OpStateExt: XML parse error', error=str(e))
            return None

        result_code = -1
        state_code: int | None = None
        out_sum: str | None = None

        for el in root.iter():
            if _xml_local(el.tag) != 'Result':
                continue
            for ch in el:
                if _xml_local(ch.tag) == 'Code' and ch.text is not None:
                    try:
                        result_code = int(ch.text.strip())
                    except ValueError:
                        result_code = -1
            break

        for el in root.iter():
            if _xml_local(el.tag) != 'State':
                continue
            for ch in el:
                if _xml_local(ch.tag) == 'Code' and ch.text is not None:
                    try:
                        state_code = int(ch.text.strip())
                    except ValueError:
                        state_code = None
            break

        for el in root.iter():
            if _xml_local(el.tag) != 'Info':
                continue
            for ch in el:
                if _xml_local(ch.tag) == 'OutSum' and ch.text and ch.text.strip():
                    out_sum = ch.text.strip()
            break

        return OpStateExtResult(result_code=result_code, state_code=state_code, out_sum=out_sum)

    async def fetch_op_state_ext(self, inv_id: int) -> OpStateExtResult | None:
        """
        Запрос статуса операции (только основной режим, не тестовые платежи).
        State.Code 100 — успешно оплачено.
        """
        params = {
            'MerchantLogin': self.login,
            'InvoiceID': inv_id,
            'Signature': self.build_op_state_ext_signature(inv_id),
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.get(OPSTATE_EXT_URL, params=params)
            response.raise_for_status()
        except httpx.HTTPError as e:
            logger.warning('Robokassa OpStateExt: HTTP error', inv_id=inv_id, error=str(e))
            return None
        return self.parse_op_state_ext_xml(response.text)

    @staticmethod
    def out_sum_matches_kopeks(out_sum_raw: str, amount_kopeks: int) -> bool:
        """Сравнение суммы из уведомления/API с ожидаемыми копейками (учёт 6 знаков в OutSum)."""
        try:
            paid = (Decimal(str(out_sum_raw).strip().replace(',', '.')) * Decimal(100)).quantize(
                Decimal('1'), rounding=ROUND_HALF_UP
            )
            return int(paid) == int(amount_kopeks)
        except Exception:
            return False

    def is_trusted_ip(self, client_ip: str) -> bool:
        """Проверка, что запрос на Result URL пришёл с IP Robokassa (опционально)."""
        if not client_ip:
            return False
        trusted = getattr(settings, 'ROBOKASSA_TRUSTED_IPS', '') or ''
        if not trusted:
            return True
        allowed = {ip.strip() for ip in trusted.split(',') if ip.strip()}
        return not allowed or client_ip.strip() in allowed

    def build_payment_url(
        self,
        inv_id: int,
        out_sum: float,
        description: str,
        email: str | None = None,
        culture: str = 'ru',
        is_test: bool | None = None,
        receipt_item_name: str | None = None,
    ) -> str:
        """
        Формирует URL для перенаправления на оплату Robokassa.
        При включённой фискализации добавляет параметр Receipt и учитывает его в подписи.
        """
        receipt_json: str | None = None
        receipt_encoded: str | None = None
        if getattr(settings, 'ROBOKASSA_RECEIPT_ENABLED', False):
            item_name = receipt_item_name or getattr(
                settings, 'ROBOKASSA_RECEIPT_ITEM_NAME', ''
            ).strip() or getattr(settings, 'PAYMENT_BALANCE_DESCRIPTION', 'Пополнение баланса')
            receipt_json = self._build_receipt_json(out_sum, item_name)
            receipt_encoded = quote(receipt_json, safe='')

        # OutSum в подписи и в URL должен совпадать (формат с двумя знаками после запятой)
        out_sum_str = f'{out_sum:.2f}'
        signature = self.build_signature_for_request(
            out_sum, inv_id, receipt_json=receipt_json
        )
        params = {
            'MerchantLogin': self.login,
            'OutSum': out_sum_str,
            'InvId': inv_id,
            'Description': description,
            'SignatureValue': signature,
            'Culture': culture,
        }
        if is_test if is_test is not None else getattr(settings, 'ROBOKASSA_IS_TEST', False):
            params['IsTest'] = 1
        if email:
            params['Email'] = email
        base = ROBOKASSA_BASE_URL
        query = urlencode(params)
        if receipt_encoded:
            query += '&Receipt=' + receipt_encoded
        return f'{base}?{query}'


robokassa_service = RobokassaService()
