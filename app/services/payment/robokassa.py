"""Mixin для интеграции с Robokassa."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from importlib import import_module
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import PaymentMethod, TransactionType
from app.services.robokassa_service import robokassa_service
from app.services.subscription_auto_purchase_service import (
    auto_purchase_saved_cart_after_topup,
)
from app.utils.payment_logger import payment_logger as logger
from app.utils.user_utils import format_referrer_info


class RobokassaPaymentMixin:
    """Mixin для работы с платежами Robokassa."""

    async def create_robokassa_payment(
        self,
        db: AsyncSession,
        *,
        user_id: int,
        amount_kopeks: int,
        description: str = 'Пополнение баланса',
        email: str | None = None,
    ) -> dict[str, Any] | None:
        """
        Создаёт платёж Robokassa.
        InvId генерируется как уникальное целое число (требование Robokassa).
        """
        if not settings.is_robokassa_enabled():
            logger.error('Robokassa не настроен')
            return None

        if amount_kopeks < settings.ROBOKASSA_MIN_AMOUNT_KOPEKS:
            logger.warning(
                'Robokassa: сумма меньше минимальной',
                amount_kopeks=amount_kopeks,
                min_kopeks=settings.ROBOKASSA_MIN_AMOUNT_KOPEKS,
            )
            return None

        if amount_kopeks > settings.ROBOKASSA_MAX_AMOUNT_KOPEKS:
            logger.warning(
                'Robokassa: сумма больше максимальной',
                amount_kopeks=amount_kopeks,
                max_kopeks=settings.ROBOKASSA_MAX_AMOUNT_KOPEKS,
            )
            return None

        # Уникальный InvId (целое число для Robokassa)
        inv_id = int(datetime.now(UTC).timestamp() * 1000) % (10**9)
        if inv_id < 100000:
            inv_id += 100000
        order_id = f'rk_{user_id}_{uuid.uuid4().hex[:12]}'
        amount_rubles = amount_kopeks / 100
        currency = settings.ROBOKASSA_CURRENCY
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.ROBOKASSA_PAYMENT_TIMEOUT_SECONDS)

        receipt_item_name = (
            getattr(settings, 'ROBOKASSA_RECEIPT_ITEM_NAME', '').strip()
            or getattr(settings, 'PAYMENT_BALANCE_DESCRIPTION', 'Пополнение баланса')
        )
        payment_url = robokassa_service.build_payment_url(
            inv_id=inv_id,
            out_sum=amount_rubles,
            description=description,
            email=email,
            is_test=settings.ROBOKASSA_IS_TEST,
            receipt_item_name=receipt_item_name,
        )

        robokassa_crud = import_module('app.database.crud.robokassa')
        local_payment = await robokassa_crud.create_robokassa_payment(
            db=db,
            user_id=user_id,
            inv_id=inv_id,
            order_id=order_id,
            amount_kopeks=amount_kopeks,
            currency=currency,
            description=description,
            payment_url=payment_url,
            expires_at=expires_at,
        )

        logger.info(
            'Robokassa: создан платёж inv_id= order_id= user_id= amount=',
            inv_id=inv_id,
            order_id=order_id,
            user_id=user_id,
            amount_rubles=amount_rubles,
        )

        return {
            'order_id': order_id,
            'inv_id': inv_id,
            'amount_kopeks': amount_kopeks,
            'amount_rubles': amount_rubles,
            'currency': currency,
            'payment_url': payment_url,
            'expires_at': expires_at.isoformat(),
            'local_payment_id': local_payment.id,
        }

    async def process_robokassa_webhook(
        self,
        db: AsyncSession,
        *,
        out_sum: str,
        inv_id: str,
        signature_value: str,
        client_ip: str | None = None,
    ) -> bool:
        """
        Обрабатывает уведомление Result URL от Robokassa.
        Ответ сервера должен быть: OK{InvId}.
        Документация: https://docs.robokassa.ru/ru/notifications-and-redirects
        """
        try:
            if client_ip and not robokassa_service.is_trusted_ip(client_ip):
                logger.warning(
                    'Robokassa webhook: запрос с недоверенного IP (очисти ROBOKASSA_TRUSTED_IPS или добавь этот IP)',
                    client_ip=client_ip,
                    inv_id=inv_id,
                )
                return False
            if not robokassa_service.verify_result_signature(out_sum, inv_id, signature_value):
                logger.warning(
                    'Robokassa webhook: неверная подпись (проверь ROBOKASSA_PASSWORD_2 в .env и Пароль#2 в кабинете)',
                    inv_id=inv_id,
                    out_sum=out_sum,
                )
                return False

            robokassa_crud = import_module('app.database.crud.robokassa')
            try:
                inv_id_int = int(inv_id)
            except ValueError:
                logger.warning('Robokassa webhook: неверный InvId', inv_id=inv_id)
                return False

            payment = await robokassa_crud.get_robokassa_payment_by_inv_id(db, inv_id_int)
            if not payment:
                logger.warning(
                    'Robokassa webhook: платёж не найден в БД (другой сервер/инстанс или платёж не сохранился)',
                    inv_id=inv_id,
                )
                return False

            if payment.is_paid:
                logger.info('Robokassa webhook: платёж уже обработан inv_id=', inv_id=inv_id)
                return True

            amount_float = float(out_sum)
            expected = payment.amount_kopeks / 100
            if abs(amount_float - expected) > 0.01:
                logger.warning(
                    'Robokassa webhook: несоответствие суммы ожидалось= получено=',
                    expected=expected,
                    received=amount_float,
                    inv_id=inv_id,
                )
                return False

            await robokassa_crud.update_robokassa_payment_status(
                db=db,
                payment=payment,
                status='success',
                is_paid=True,
            )

            return await self._finalize_robokassa_payment(db, payment, trigger='webhook')
        except Exception as e:
            logger.exception('Robokassa webhook: ошибка обработки', e=e)
            return False

    async def _finalize_robokassa_payment(
        self,
        db: AsyncSession,
        payment: Any,
        *,
        trigger: str,
    ) -> bool:
        """Создаёт транзакцию, начисляет баланс и отправляет уведомления."""
        payment_module = import_module('app.services.payment_service')
        robokassa_crud = import_module('app.database.crud.robokassa')

        if payment.transaction_id:
            logger.info(
                'Robokassa платёж уже привязан к транзакции (trigger=)',
                inv_id=payment.inv_id,
                trigger=trigger,
            )
            return True

        user = await payment_module.get_user_by_id(db, payment.user_id)
        if not user:
            logger.error(
                'Пользователь не найден для Robokassa платежа',
                user_id=payment.user_id,
                inv_id=payment.inv_id,
                trigger=trigger,
            )
            return False

        transaction = await payment_module.create_transaction(
            db,
            user_id=payment.user_id,
            type=TransactionType.DEPOSIT,
            amount_kopeks=payment.amount_kopeks,
            description=f'Пополнение через Robokassa (#{payment.inv_id})',
            payment_method=PaymentMethod.ROBOKASSA,
            external_id=str(payment.inv_id),
            is_completed=True,
            created_at=getattr(payment, 'created_at', None),
        )

        await robokassa_crud.update_robokassa_payment_status(
            db=db,
            payment=payment,
            status=payment.status,
            is_paid=True,
            transaction_id=transaction.id,
        )

        old_balance = user.balance_kopeks
        was_first_topup = not user.has_made_first_topup
        user.balance_kopeks += payment.amount_kopeks
        user.updated_at = datetime.now(UTC)
        promo_group = user.get_primary_promo_group()
        subscription = getattr(user, 'subscription', None)
        referrer_info = format_referrer_info(user)
        topup_status = 'Первое пополнение' if was_first_topup else 'Пополнение'

        await db.commit()

        try:
            from app.services.referral_service import process_referral_topup

            await process_referral_topup(db, user.id, payment.amount_kopeks, getattr(self, 'bot', None))
        except Exception as error:
            logger.error('Ошибка обработки реферального пополнения Robokassa', error=error)

        if was_first_topup and not user.has_made_first_topup:
            user.has_made_first_topup = True
            await db.commit()

        await db.refresh(user)
        await db.refresh(payment)

        if getattr(self, 'bot', None):
            try:
                from app.services.admin_notification_service import AdminNotificationService

                notification_service = AdminNotificationService(self.bot)
                await notification_service.send_balance_topup_notification(
                    user,
                    transaction,
                    old_balance,
                    topup_status=topup_status,
                    referrer_info=referrer_info,
                    subscription=subscription,
                    promo_group=promo_group,
                    db=db,
                )
            except Exception as error:
                logger.error('Ошибка отправки админ уведомления Robokassa', error=error)

        if getattr(self, 'bot', None) and user.telegram_id:
            try:
                keyboard = await self.build_topup_success_keyboard(user)
                display_name = settings.get_robokassa_display_name()
                await self.bot.send_message(
                    user.telegram_id,
                    (
                        '✅ <b>Пополнение успешно!</b>\n\n'
                        f'💰 Сумма: {settings.format_price(payment.amount_kopeks)}\n'
                        f'💳 Способ: {display_name}\n'
                        f'🆔 Транзакция: {transaction.id}\n\n'
                        'Баланс пополнен автоматически!'
                    ),
                    parse_mode='HTML',
                    reply_markup=keyboard,
                )
            except Exception as error:
                logger.error('Ошибка отправки уведомления пользователю Robokassa', error=error)

        try:
            from aiogram import types
            from app.services.user_cart_service import user_cart_service

            has_saved_cart = await user_cart_service.has_user_cart(user.id)
            auto_purchase_success = False
            if has_saved_cart:
                try:
                    auto_purchase_success = await auto_purchase_saved_cart_after_topup(
                        db, user, bot=getattr(self, 'bot', None)
                    )
                except Exception as auto_error:
                    logger.error(
                        'Ошибка автоматической покупки подписки после Robokassa',
                        user_id=user.id,
                        auto_error=auto_error,
                        exc_info=True,
                    )
            if has_saved_cart and not auto_purchase_success and getattr(self, 'bot', None) and user.telegram_id:
                from app.localization.texts import get_texts
                texts = get_texts(user.language)
                keyboard = types.InlineKeyboardMarkup(
                    inline_keyboard=[
                        [
                            types.InlineKeyboardButton(
                                text=texts.t('BALANCE_TOPUP_CART_BUTTON', '🛒 Продолжить оформление'),
                                callback_data='return_to_saved_cart',
                            )
                        ],
                        [types.InlineKeyboardButton(text='🏠 Главное меню', callback_data='back_to_menu')],
                    ]
                )
                await self.bot.send_message(
                    chat_id=user.telegram_id,
                    text=f'✅ Баланс пополнен на {settings.format_price(payment.amount_kopeks)}!\n\n'
                    + texts.t('BALANCE_TOPUP_CART_REMINDER', 'У вас есть незавершенное оформление подписки. Вернуться?'),
                    reply_markup=keyboard,
                )
        except Exception as error:
            logger.error('Ошибка при работе с корзиной после Robokassa', user_id=user.id, error=error, exc_info=True)

        logger.info(
            '✅ Обработан Robokassa платёж для пользователя (trigger=)',
            inv_id=payment.inv_id,
            user_id=payment.user_id,
            trigger=trigger,
        )
        return True
