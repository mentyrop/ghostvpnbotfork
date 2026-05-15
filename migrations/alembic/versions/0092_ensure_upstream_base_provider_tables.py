"""ensure upstream-base provider tables exist (apple_transactions, jupiter/donut/lava_payments)

В нашем форке исторически у некоторых проданских БД `alembic_version` стоял на
ветке наших ensure-миграций (старые 0080+ с down_revision='0078'), которая
обходила upstream-овские 0068 / 0072..0074. В таких БД эти миграции числились
«применёнными», но физически таблицы `apple_transactions`, `jupiter_payments`,
`donut_payments`, `lava_payments` НЕ создавались.

После rebase нашей ветки поверх upstream v3.55.0 (см. миграции 0083..0091)
эти 4 таблицы нужны upstream-овской `0075_rebuild_apple_iap_ledgers` (она
добавляет колонки в `apple_transactions`). Чтобы при `0074 -> 0075` не падала
ошибка `relation "apple_transactions" does not exist` на таких БД, эта
миграция-предохранитель идемпотентно создаёт недостающие провайдерские
таблицы. На clean-install и нормальных upgraded БД это no-op (таблицы уже есть).

Revision ID: 0092
Revises: 0091
Create Date: 2026-05-15

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0092'
down_revision: Union[str, None] = '0091'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


_APPLE_TRANSACTIONS_DDL = """
CREATE TABLE IF NOT EXISTS apple_transactions (
    id SERIAL PRIMARY KEY,
    user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    transaction_id VARCHAR(64) UNIQUE NOT NULL,
    original_transaction_id VARCHAR(64),
    product_id VARCHAR(128) NOT NULL,
    bundle_id VARCHAR(255) NOT NULL,
    amount_kopeks INTEGER NOT NULL,
    environment VARCHAR(16) NOT NULL,
    status VARCHAR(50) DEFAULT 'verified',
    is_paid BOOLEAN DEFAULT TRUE,
    paid_at TIMESTAMP WITH TIME ZONE,
    refunded_at TIMESTAMP WITH TIME ZONE,
    transaction_id_fk INTEGER REFERENCES transactions(id),
    metadata_json JSON,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now()
);
CREATE INDEX IF NOT EXISTS ix_apple_transactions_transaction_id          ON apple_transactions (transaction_id);
CREATE INDEX IF NOT EXISTS ix_apple_transactions_original_transaction_id ON apple_transactions (original_transaction_id);
CREATE INDEX IF NOT EXISTS ix_apple_transactions_user_id                 ON apple_transactions (user_id);
"""

_JUPITER_PAYMENTS_DDL = """
CREATE TABLE IF NOT EXISTS jupiter_payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    order_id VARCHAR(64) UNIQUE NOT NULL,
    jupiter_transaction_id VARCHAR(128) UNIQUE,
    amount_kopeks INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'RUB',
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    payment_url TEXT,
    payment_method VARCHAR(32),
    metadata_json JSON,
    callback_payload JSON,
    paid_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    transaction_id INTEGER REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS ix_jupiter_payments_user_id                ON jupiter_payments (user_id);
CREATE INDEX IF NOT EXISTS ix_jupiter_payments_order_id               ON jupiter_payments (order_id);
CREATE INDEX IF NOT EXISTS ix_jupiter_payments_jupiter_transaction_id ON jupiter_payments (jupiter_transaction_id);
"""

_DONUT_PAYMENTS_DDL = """
CREATE TABLE IF NOT EXISTS donut_payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    order_id VARCHAR(64) UNIQUE NOT NULL,
    donut_transaction_id VARCHAR(128) UNIQUE,
    amount_kopeks INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'RUB',
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    payment_url TEXT,
    payment_method VARCHAR(32),
    metadata_json JSON,
    callback_payload JSON,
    paid_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    transaction_id INTEGER REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS ix_donut_payments_user_id              ON donut_payments (user_id);
CREATE INDEX IF NOT EXISTS ix_donut_payments_order_id             ON donut_payments (order_id);
CREATE INDEX IF NOT EXISTS ix_donut_payments_donut_transaction_id ON donut_payments (donut_transaction_id);
"""

_LAVA_PAYMENTS_DDL = """
CREATE TABLE IF NOT EXISTS lava_payments (
    id SERIAL PRIMARY KEY,
    user_id INTEGER REFERENCES users(id) ON DELETE SET NULL,
    order_id VARCHAR(64) UNIQUE NOT NULL,
    lava_invoice_id VARCHAR(128) UNIQUE,
    amount_kopeks INTEGER NOT NULL,
    currency VARCHAR(10) NOT NULL DEFAULT 'RUB',
    description TEXT,
    status VARCHAR(32) NOT NULL DEFAULT 'pending',
    is_paid BOOLEAN NOT NULL DEFAULT FALSE,
    payment_url TEXT,
    payment_method VARCHAR(32),
    metadata_json JSON,
    callback_payload JSON,
    paid_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT now(),
    transaction_id INTEGER REFERENCES transactions(id)
);
CREATE INDEX IF NOT EXISTS ix_lava_payments_user_id         ON lava_payments (user_id);
CREATE INDEX IF NOT EXISTS ix_lava_payments_order_id        ON lava_payments (order_id);
CREATE INDEX IF NOT EXISTS ix_lava_payments_lava_invoice_id ON lava_payments (lava_invoice_id);
"""


def upgrade() -> None:
    bind = op.get_bind()
    if bind.dialect.name != 'postgresql':
        # На SQLite/dev — пропускаем, там схема собирается через metadata.create_all
        return

    for ddl in (
        _APPLE_TRANSACTIONS_DDL,
        _JUPITER_PAYMENTS_DDL,
        _DONUT_PAYMENTS_DDL,
        _LAVA_PAYMENTS_DDL,
    ):
        op.execute(sa.text(ddl))


def downgrade() -> None:
    # Идемпотентная safety-net: даунгрейд не дропает таблицы, чтобы случайно
    # не уничтожить данные провайдеров. Полное удаление — через 0068/0072..0074.
    pass
