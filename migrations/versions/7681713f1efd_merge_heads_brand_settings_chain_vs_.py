"""merge heads brand-settings chain vs onboarding-voice-assets chain

Revision ID: 7681713f1efd
Revises: 16144c22ef71, 8c73e7df60d7
Create Date: 2026-09-19 21:44:56.699559

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '7681713f1efd'
down_revision: Union[str, None] = ('16144c22ef71', '8c73e7df60d7')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
