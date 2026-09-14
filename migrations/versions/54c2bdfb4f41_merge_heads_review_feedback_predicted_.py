"""merge heads review feedback predicted engagement vs onboarding voice assets

Revision ID: 54c2bdfb4f41
Revises: 88fcfa95b048, a3f7c9e1d204
Create Date: 2026-09-14 23:58:30.395056

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '54c2bdfb4f41'
down_revision: Union[str, None] = ('88fcfa95b048', 'a3f7c9e1d204')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
