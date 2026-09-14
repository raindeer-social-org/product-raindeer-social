"""merge heads onboarding-voice-assets chain vs x-oauth chain

Revision ID: 8c73e7df60d7
Revises: 54c2bdfb4f41, 99350fa6fc39
Create Date: 2026-09-15 00:54:36.628236

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8c73e7df60d7'
down_revision: Union[str, None] = ('54c2bdfb4f41', '99350fa6fc39')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
