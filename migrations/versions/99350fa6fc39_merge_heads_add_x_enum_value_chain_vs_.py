"""merge heads add-x-enum-value chain vs social-platform-new-values chain

Revision ID: 99350fa6fc39
Revises: 35a1cae89d35, e1bbd7e93524
Create Date: 2026-09-15 00:30:42.393256

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '99350fa6fc39'
down_revision: Union[str, None] = ('35a1cae89d35', 'e1bbd7e93524')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
