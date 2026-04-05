"""Сервис для работы с Robokassa (форма оплаты и проверка Result URL).

Документация:
- Интерфейс оплаты: https://docs.robokassa.ru/ru/pay-interface
- Уведомления: https://docs.robokassa.ru/ru/notifications-and-redirects
- Фискализация (чеки): https://docs.robokassa.ru/ru/fiscalization
"""

import hashlib
import json
from urllib.parse import quote, urlencode

import structlog

from app.config import settings


logger = structlog.get_logger(__name__)

# Базовый URL (тест через параметр IsTest=1)
ROBOKASSA_BASE_URL = 'https://auth.robokassa.ru/Merchant/Index.aspx'

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
        """
        if shp_sorted:
            shp_part = ':'.join(f'{k}={v}' for k, v in shp_sorted)
            sign_str = f'{out_sum}:{inv_id}:{self.password2}:{shp_part}'
        else:
            sign_str = f'{out_sum}:{inv_id}:{self.password2}'
        expected = hashlib.md5(sign_str.encode('utf-8')).hexdigest().lower()
        received = (signature_value or '').strip().lower()
        return received == expected

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
