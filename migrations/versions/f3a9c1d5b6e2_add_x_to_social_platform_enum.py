"""add X to social_platform enum

Revision ID: f3a9c1d5b6e2
Revises: 5b29b584c4fa
Create Date: 2026-08-27T09:45:00

XProvider, SUPPORTED_PLATFORMS, and the OAuth registry entry for "x" have
existed since #30/#10, but the social_platform Postgres enum was only ever
created with 'LINKEDIN' (007_social_accounts.py) — SocialAccount rows for
X were never actually storable. Value is 'X' (uppercase), matching
SocialPlatform's *member name*, not its .value ("x") — SQLAlchemy's
`Enum(SocialPlatform, ...)` column (no `values_callable` override) stores
`.name`, the same convention 'LINKEDIN' already follows.
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'f3a9c1d5b6e2'
down_revision: Union[str, None] = '5b29b584c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE social_platform ADD VALUE IF NOT EXISTS 'X'")


def downgrade() -> None:
    # Postgres has no DROP VALUE for enums — downgrading this cleanly
    # would require rebuilding the type and every column that uses it.
    # Not implemented; matches this repo's existing convention for
    # additive-enum-value migrations elsewhere.
    pass
