"""social_platform meta values

Revision ID: a1b2c3d4e5f6
Revises: 5b29b584c4fa
Create Date: 2026-08-27 00:00:00.000000

Issues #108/#109/#110 add Instagram, Threads, and Facebook Page publishing
alongside LinkedIn/X — apps/api/models/social_account.py::SocialPlatform
needs a matching row for each so a SocialAccount can actually be stored for
the new platforms (same reason ad4c424c0dc8's social_accounts migration
only defined 'LINKEDIN' for the one platform that existed at the time).
"""
from typing import Sequence, Union

from alembic import op

# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4e5f6'
down_revision: Union[str, None] = '5b29b584c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_NEW_VALUES = ('INSTAGRAM', 'THREADS', 'FACEBOOK')


def upgrade() -> None:
    for value in _NEW_VALUES:
        op.execute(f"ALTER TYPE social_platform ADD VALUE IF NOT EXISTS '{value}'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE, so removing these means
    # rebuilding the enum from scratch — same lossy-on-downgrade tradeoff
    # 75d69ba778a0's agent_type downgrade and c41e72b7ec17's pipeline_stage
    # downgrade already accept, and fails as expected if any social_accounts
    # row already uses one of these values.
    op.execute("ALTER TYPE social_platform RENAME TO social_platform_old")
    op.execute("CREATE TYPE social_platform AS ENUM ('LINKEDIN')")
    op.execute(
        "ALTER TABLE social_accounts "
        "ALTER COLUMN platform TYPE social_platform "
        "USING platform::text::social_platform"
    )
    op.execute("DROP TYPE social_platform_old")
