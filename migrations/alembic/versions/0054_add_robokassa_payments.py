"""add robokassa_payments table

Revision ID: 0054
Revises: 0053
Create Date: 2026-04-05

Adds robokassa_payments table for Robokassa payment integration.
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0054'
down_revision: Union[str, None] = '0053'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def upgrade() -> None:
    if _has_table('robokassa_payments'):
        return

    op.create_table(
        'robokassa_payments',
        sa.Column('id', sa.Integer(), autoincrement=True, nullable=False),
        sa.Column('user_id', sa.Integer(), nullable=False),
        sa.Column('inv_id', sa.Integer(), nullable=False),
        sa.Column('order_id', sa.String(64), nullable=False),
        sa.Column('amount_kopeks', sa.Integer(), nullable=False),
        sa.Column('currency', sa.String(10), nullable=False, server_default='RUB'),
        sa.Column('description', sa.Text(), nullable=True),
        sa.Column('status', sa.String(32), nullable=False, server_default='pending'),
        sa.Column('is_paid', sa.Boolean(), nullable=True, server_default=sa.text('false')),
        sa.Column('payment_url', sa.Text(), nullable=True),
        sa.Column('paid_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('transaction_id', sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(['transaction_id'], ['transactions.id']),
        sa.ForeignKeyConstraint(['user_id'], ['users.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('inv_id', name='uq_robokassa_payments_inv_id'),
        sa.UniqueConstraint('order_id', name='uq_robokassa_payments_order_id'),
    )
    op.create_index('ix_robokassa_payments_inv_id', 'robokassa_payments', ['inv_id'])
    op.create_index('ix_robokassa_payments_order_id', 'robokassa_payments', ['order_id'])
    op.create_index('ix_robokassa_payments_user_id', 'robokassa_payments', ['user_id'])


def downgrade() -> None:
    if not _has_table('robokassa_payments'):
        return
    op.drop_index('ix_robokassa_payments_user_id', table_name='robokassa_payments')
    op.drop_index('ix_robokassa_payments_order_id', table_name='robokassa_payments')
    op.drop_index('ix_robokassa_payments_inv_id', table_name='robokassa_payments')
    op.drop_table('robokassa_payments')
