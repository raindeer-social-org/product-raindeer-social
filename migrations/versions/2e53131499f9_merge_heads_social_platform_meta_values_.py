"""merge heads social platform meta values vs social platform new values

Revision ID: 2e53131499f9
Revises: 0bf6ea93886f, b7c9e2a4f1d3
Create Date: 2026-09-15 00:20:36.420491

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '2e53131499f9'
down_revision: Union[str, None] = ('0bf6ea93886f', 'b7c9e2a4f1d3')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
