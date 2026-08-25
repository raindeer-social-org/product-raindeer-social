"""merge heads (weekly report vs brand pdf/post-media/review-feedback merge)

Revision ID: 5b29b584c4fa
Revises: 0d2a5fb92eb0, 82c4c5183a33
Create Date: 2026-08-25 22:36:28.557670

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '5b29b584c4fa'
down_revision: Union[str, None] = ('0d2a5fb92eb0', '82c4c5183a33')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
