"""merge heads social platform meta values vs post variant group

Revision ID: e1bbd7e93524
Revises: 0bf6ea93886f, 35bb32046dba
Create Date: 2026-09-15 00:04:15.388997

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'e1bbd7e93524'
down_revision: Union[str, None] = ('0bf6ea93886f', '35bb32046dba')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
