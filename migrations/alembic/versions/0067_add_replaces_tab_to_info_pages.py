"""add replaces_tab to info_pages

Revision ID: 0070
Revises: 0069
Create Date: 2026-04-21

"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = '0070'
down_revision: Union[str, None] = '0069'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'info_pages',
        sa.Column('replaces_tab', sa.String(20), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('info_pages', 'replaces_tab')
