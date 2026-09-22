"""make onboarding_voice_answers.audio_url nullable

Revision ID: 487ef7daef58
Revises: 0cb88eee70c5
Create Date: 2026-09-22 11:05:00.000000

Re-hosting a recorded voice answer's raw audio is best-effort (see
create_voice_answer in apps/api/routers/onboarding.py) — a StorageProvider
outage must never cost the brand a transcript that already succeeded.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '487ef7daef58'
down_revision: Union[str, None] = '0cb88eee70c5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        'onboarding_voice_answers',
        'audio_url',
        existing_type=sa.String(),
        nullable=True,
    )


def downgrade() -> None:
    op.alter_column(
        'onboarding_voice_answers',
        'audio_url',
        existing_type=sa.String(),
        nullable=False,
    )
