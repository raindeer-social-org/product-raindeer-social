"""merge heads (brand pdf export, post media, publish/engagement/analytics chain)

Revision ID: c4d732c135f1
Revises: fa23800d332d, 104119cc2693, 63bac4f4c66f
Create Date: 2026-08-25 11:42:34.753031

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c4d732c135f1'
down_revision: Union[str, None] = ('fa23800d332d', '104119cc2693', '63bac4f4c66f')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
