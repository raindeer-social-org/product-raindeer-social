"""merge heads review feedback predicted engagement vs brand settings

Revision ID: 16144c22ef71
Revises: 88fcfa95b048, f3f97cb5fdf2
Create Date: 2026-09-15 00:09:10.782891

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '16144c22ef71'
down_revision: Union[str, None] = ('88fcfa95b048', 'f3f97cb5fdf2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
