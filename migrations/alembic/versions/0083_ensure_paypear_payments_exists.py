"""compat: ensure paypear table and revoke timestamp column exist

Revision ID: 0075
Revises: 0074
Create Date: 2026-05-10
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0083'
down_revision: Union[str, None] = '0082'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def _has_table(table: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    return table in inspector.get_table_names()


def _has_column(table: str, column: str) -> bool:
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    try:
        cols = inspector.get_columns(table)
    except Exception:
        return False
    return any(col.get('name') == column for col in cols)


def upgrade() -> None:
    if _has_table('paypear_payments'):
        return

    op.create_table(
        'paypear_payments',
        sa.Column('id', sa.Integer(), primary_key=True, autoincrement=True),
        sa.Column('user_id', sa.Integer(), sa.ForeignKey('users.id', ondelete='SET NULL'), nullable=True),
        sa.Column('order_id', sa.String(64), nullable=False),
        sa.Column('paypear_id', sa.String(64), nullable=True),
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
        sa.UniqueConstraint('order_id', name='uq_paypear_payments_order_id'),
        sa.UniqueConstraint('paypear_id', name='uq_paypear_payments_paypear_id'),
    )

    op.create_index('ix_paypear_payments_user_id', 'paypear_payments', ['user_id'])
    op.create_index('ix_paypear_payments_order_id', 'paypear_payments', ['order_id'])
    op.create_index('ix_paypear_payments_paypear_id', 'paypear_payments', ['paypear_id'])

    # Compatibility patch: some forks used an older custom "0071" revision id,
    # so upstream's 0071 migration (last_revoke_at) may have been skipped.
    if _has_table('subscriptions') and not _has_column('subscriptions', 'last_revoke_at'):
        op.add_column('subscriptions', sa.Column('last_revoke_at', sa.DateTime(timezone=True), nullable=True))


def downgrade() -> None:
    if _has_table('subscriptions') and _has_column('subscriptions', 'last_revoke_at'):
        op.drop_column('subscriptions', 'last_revoke_at')
    if _has_table('paypear_payments'):
        op.drop_index('ix_paypear_payments_paypear_id', table_name='paypear_payments')
        op.drop_index('ix_paypear_payments_order_id', table_name='paypear_payments')
        op.drop_index('ix_paypear_payments_user_id', table_name='paypear_payments')
        op.drop_table('paypear_payments')
