"""merge heads social-platform-new-values chain vs brand-settings chain

Revision ID: d017fe5c281d
Revises: 2e53131499f9, 7681713f1efd
Create Date: 2026-09-20 00:14:19.636619

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'd017fe5c281d'
down_revision: Union[str, None] = ('2e53131499f9', '7681713f1efd')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
