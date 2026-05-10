"""add page_type to info_pages

Revision ID: 0077
Revises: 0076
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0077'
down_revision: Union[str, None] = '0076'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            'SELECT EXISTS (SELECT 1 FROM information_schema.columns '
            "WHERE table_name = 'info_pages' AND column_name = 'page_type')"
        )
    ).scalar()
    if not exists:
        op.add_column(
            'info_pages',
            sa.Column('page_type', sa.String(20), nullable=False, server_default='page'),
        )


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            'SELECT EXISTS (SELECT 1 FROM information_schema.columns '
            "WHERE table_name = 'info_pages' AND column_name = 'page_type')"
        )
    ).scalar()
    if exists:
        op.drop_column('info_pages', 'page_type')
