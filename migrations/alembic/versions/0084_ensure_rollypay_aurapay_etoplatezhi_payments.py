"""ensure rollypay / aurapay / etoplatezhi payment tables exist

Revision ID: 0084
Revises: 0083
Create Date: 2026-05-10

If alembic_version was advanced past 0080–0082 without CREATE running (stamp,
failed upgrade, restored DB), those tables can be missing while revision says
applied. Idempotent CREATE — safe no-op when tables already exist.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0084'
down_revision: Union[str, None] = '0083'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


_PAYMENT_TABLE_COLUMNS = (
    sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
    sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
    sa.Column('order_id', sa.String(64), unique=True, nullable=False, index=True),
    sa.Column('amount_kopeks', sa.Integer(), nullable=False),
    sa.Column('currency', sa.String(10), nullable=False, server_default='RUB'),
    sa.Column('description', sa.Text(), nullable=True),
    sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
    sa.Column('is_paid', sa.Boolean(), server_default=sa.text('false'), nullable=False),
    sa.Column('payment_url', sa.Text(), nullable=True),
    sa.Column('payment_method', sa.String(32), nullable=True),
    sa.Column('metadata_json', sa.JSON(), nullable=True),
    sa.Column('callback_payload', sa.JSON(), nullable=True),
    sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
    sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.func.now()),
    sa.Column('transaction_id', sa.Integer(), sa.ForeignKey('transactions.id'), nullable=True),
)


def upgrade() -> None:
    if not _has_table('rollypay_payments'):
        op.create_table(
            'rollypay_payments',
            *_PAYMENT_TABLE_COLUMNS[:3],
            sa.Column('rollypay_payment_id', sa.String(128), unique=True, nullable=True, index=True),
            *_PAYMENT_TABLE_COLUMNS[3:],
        )

    if not _has_table('aurapay_payments'):
        op.create_table(
            'aurapay_payments',
            *_PAYMENT_TABLE_COLUMNS[:3],
            sa.Column('aurapay_invoice_id', sa.String(128), unique=True, nullable=True, index=True),
            *_PAYMENT_TABLE_COLUMNS[3:],
        )

    if not _has_table('etoplatezhi_payments'):
        op.create_table(
            'etoplatezhi_payments',
            *_PAYMENT_TABLE_COLUMNS[:3],
            sa.Column('etoplatezhi_payment_id', sa.String(128), unique=True, nullable=True, index=True),
            *_PAYMENT_TABLE_COLUMNS[3:],
        )


def downgrade() -> None:
    if _has_table('etoplatezhi_payments'):
        op.drop_table('etoplatezhi_payments')
    if _has_table('aurapay_payments'):
        op.drop_table('aurapay_payments')
    if _has_table('rollypay_payments'):
        op.drop_table('rollypay_payments')
