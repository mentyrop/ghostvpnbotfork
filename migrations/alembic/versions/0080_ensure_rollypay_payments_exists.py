"""ensure rollypay_payments table exists

Revision ID: 0080
Revises: 0078
Create Date: 2026-05-10

Some deployments never applied 0059 (branching / duplicate revision ids).
Idempotent CREATE for admin payment search and RollyPay flows.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0080'
down_revision: Union[str, None] = '0078'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if not _has_table('rollypay_payments'):
        op.create_table(
            'rollypay_payments',
            sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True, index=True),
            sa.Column('order_id', sa.String(64), unique=True, nullable=False, index=True),
            sa.Column('rollypay_payment_id', sa.String(128), unique=True, nullable=True, index=True),
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
            sa.Column(
                'transaction_id', sa.Integer(), sa.ForeignKey('transactions.id'), nullable=True
            ),
        )


def downgrade() -> None:
    if _has_table('rollypay_payments'):
        op.drop_table('rollypay_payments')
