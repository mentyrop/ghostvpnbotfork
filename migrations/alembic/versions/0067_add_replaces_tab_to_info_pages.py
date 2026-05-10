"""add replaces_tab to info_pages

Revision ID: 0078
Revises: 0077
Create Date: 2026-04-21
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0078'
down_revision: Union[str, None] = '0077'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            'SELECT EXISTS (SELECT 1 FROM information_schema.columns '
            "WHERE table_name = 'info_pages' AND column_name = 'replaces_tab')"
        )
    ).scalar()
    if not exists:
        op.add_column(
            'info_pages',
            sa.Column('replaces_tab', sa.String(20), nullable=True),
        )


def downgrade() -> None:
    conn = op.get_bind()
    exists = conn.execute(
        sa.text(
            'SELECT EXISTS (SELECT 1 FROM information_schema.columns '
            "WHERE table_name = 'info_pages' AND column_name = 'replaces_tab')"
        )
    ).scalar()
    if exists:
        op.drop_column('info_pages', 'replaces_tab')
