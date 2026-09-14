"""merge heads social platform meta values vs add x enum value

Revision ID: 35a1cae89d35
Revises: 0bf6ea93886f, f3a9c1d5b6e2
Create Date: 2026-09-15 00:23:29.024991

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '35a1cae89d35'
down_revision: Union[str, None] = ('0bf6ea93886f', 'f3a9c1d5b6e2')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
