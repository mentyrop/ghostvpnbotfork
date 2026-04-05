"""CRUD для платежей Robokassa."""

from datetime import UTC, datetime, timedelta

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import settings
from app.database.models import RobokassaPayment


logger = structlog.get_logger(__name__)


async def create_robokassa_payment(
    db: AsyncSession,
    *,
    user_id: int,
    inv_id: int,
    order_id: str,
    amount_kopeks: int,
    currency: str = 'RUB',
    description: str | None = None,
    payment_url: str | None = None,
    expires_at: datetime | None = None,
) -> RobokassaPayment:
    """Создаёт запись о платеже Robokassa."""
    if expires_at is None:
        expires_at = datetime.now(UTC) + timedelta(seconds=settings.ROBOKASSA_PAYMENT_TIMEOUT_SECONDS)
    payment = RobokassaPayment(
        user_id=user_id,
        inv_id=inv_id,
        order_id=order_id,
        amount_kopeks=amount_kopeks,
        currency=currency,
        description=description,
        payment_url=payment_url,
        status='pending',
        is_paid=False,
        expires_at=expires_at,
    )
    db.add(payment)
    await db.flush()
    await db.refresh(payment)
    logger.info(
        'Создан платёж Robokassa: inv_id=, order_id=, user_id=, amount_kopeks=',
        inv_id=inv_id,
        order_id=order_id,
        user_id=user_id,
        amount_kopeks=amount_kopeks,
    )
    return payment


async def get_robokassa_payment_by_inv_id(db: AsyncSession, inv_id: int) -> RobokassaPayment | None:
    """Получить платёж по InvId (номер счёта в магазине)."""
    result = await db.execute(
        select(RobokassaPayment).where(RobokassaPayment.inv_id == inv_id)
    )
    return result.scalar_one_or_none()


async def get_latest_robokassa_inv_ids(db: AsyncSession, *, limit: int = 10) -> list[int]:
    """Последние InvId в таблице (диагностика вебхука)."""
    result = await db.execute(
        select(RobokassaPayment.inv_id).order_by(RobokassaPayment.id.desc()).limit(limit)
    )
    return [row[0] for row in result.all()]


async def get_robokassa_payment_by_order_id(db: AsyncSession, order_id: str) -> RobokassaPayment | None:
    """Получить платёж по нашему order_id."""
    result = await db.execute(
        select(RobokassaPayment).where(RobokassaPayment.order_id == order_id)
    )
    return result.scalar_one_or_none()


async def get_robokassa_payment_by_id(db: AsyncSession, payment_id: int) -> RobokassaPayment | None:
    """Получить платёж по внутреннему id."""
    result = await db.execute(
        select(RobokassaPayment).where(RobokassaPayment.id == payment_id)
    )
    return result.scalar_one_or_none()


async def update_robokassa_payment_status(
    db: AsyncSession,
    payment: RobokassaPayment,
    *,
    status: str,
    is_paid: bool = False,
    transaction_id: int | None = None,
) -> RobokassaPayment:
    """Обновить статус платежа Robokassa."""
    payment.status = status
    payment.is_paid = is_paid
    if transaction_id is not None:
        payment.transaction_id = transaction_id
    if is_paid:
        payment.paid_at = datetime.now(UTC)
    payment.updated_at = datetime.now(UTC)
    await db.flush()
    await db.refresh(payment)
    logger.info(
        'Обновлён платёж Robokassa: inv_id=, status=, is_paid=',
        inv_id=payment.inv_id,
        status=status,
        is_paid=is_paid,
    )
    return payment


async def get_pending_robokassa_payments(db: AsyncSession, user_id: int) -> list[RobokassaPayment]:
    """Список ожидающих платежей пользователя."""
    result = await db.execute(
        select(RobokassaPayment).where(
            RobokassaPayment.user_id == user_id,
            RobokassaPayment.status == 'pending',
            RobokassaPayment.is_paid.is_(False),
        ).order_by(RobokassaPayment.created_at.desc())
    )
    return list(result.scalars().all())


async def get_user_robokassa_payments(
    db: AsyncSession,
    user_id: int,
    limit: int = 50,
) -> list[RobokassaPayment]:
    """Платежи пользователя по Robokassa."""
    result = await db.execute(
        select(RobokassaPayment)
        .where(RobokassaPayment.user_id == user_id)
        .order_by(RobokassaPayment.created_at.desc())
        .limit(limit)
    )
    return list(result.scalars().all())
