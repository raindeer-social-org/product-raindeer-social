"""merge heads review feedback predicted engagement vs post variant group

Revision ID: 0bf6ea93886f
Revises: 88fcfa95b048, 8fa8ca323102
Create Date: 2026-09-14 23:53:37.796605

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '0bf6ea93886f'
down_revision: Union[str, None] = ('88fcfa95b048', '8fa8ca323102')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
