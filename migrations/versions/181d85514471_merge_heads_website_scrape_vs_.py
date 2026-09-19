"""merge heads website-scrape vs onboarding-dynamic-questions

Revision ID: 181d85514471
Revises: 04358cec0467, c4d8f2a19b6e
Create Date: 2026-09-20 04:19:10.474853

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '181d85514471'
down_revision: Union[str, None] = ('04358cec0467', 'c4d8f2a19b6e')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
