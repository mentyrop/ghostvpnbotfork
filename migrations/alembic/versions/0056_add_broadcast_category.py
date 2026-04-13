"""add broadcast category column

Revision ID: 0056
Revises: 0054
Create Date: 2026-04-10

(Chained after fork migration 0054 robokassa_payments; avoids duplicate 0054 id with upstream.)
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0056'
down_revision: Union[str, None] = '0054'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'broadcast_history',
        sa.Column('category', sa.String(20), nullable=False, server_default='system'),
    )


def downgrade() -> None:
    op.drop_column('broadcast_history', 'category')
