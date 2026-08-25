"""merge heads (brand pdf export, post media, review feedback/rejected stage)

Revision ID: 82c4c5183a33
Revises: fa23800d332d, 104119cc2693, c41e72b7ec17
Create Date: 2026-08-25 11:58:29.365046

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '82c4c5183a33'
down_revision: Union[str, None] = ('fa23800d332d', '104119cc2693', 'c41e72b7ec17')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
