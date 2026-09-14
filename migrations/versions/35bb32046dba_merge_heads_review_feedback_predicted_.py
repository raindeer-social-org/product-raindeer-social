"""merge heads review feedback predicted engagement vs social platform meta values

Revision ID: 35bb32046dba
Revises: 88fcfa95b048, a1b2c3d4e5f6
Create Date: 2026-09-14 23:46:40.463736

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35bb32046dba'
down_revision: Union[str, None] = ('88fcfa95b048', 'a1b2c3d4e5f6')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
