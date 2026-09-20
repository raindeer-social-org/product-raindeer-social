"""merge heads onboarding dynamic-answers vs website-scrape

Revision ID: 09d2ace33584
Revises: 04358cec0467, c4d8f2a19b6e
Create Date: 2026-09-20 22:53:24.152420

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '09d2ace33584'
down_revision: Union[str, None] = ('04358cec0467', 'c4d8f2a19b6e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
