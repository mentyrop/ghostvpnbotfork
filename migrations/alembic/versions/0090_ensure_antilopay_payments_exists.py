"""ensure antilopay_payments table exists

Revision ID: 0083
Revises: 0082
Create Date: 2026-05-10

Some DBs never ran 0070 (branch / manual alembic state). Admin search and
webhooks expect this table. Idempotent CREATE aligned with 0070_create_antilopay_payments.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0090'
down_revision: Union[str, None] = '0089'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table('antilopay_payments'):
        op.create_table(
            'antilopay_payments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('order_id', sa.String(64), unique=True, nullable=False, index=True),
            sa.Column('antilopay_payment_id', sa.String(128), unique=True, nullable=True, index=True),
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


def downgrade() -> None:
    if _has_table('antilopay_payments'):
        op.drop_table('antilopay_payments')
