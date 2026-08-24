"""post rejected pipeline stage

Revision ID: c41e72b7ec17
Revises: e7d09d412f48
Create Date: 2026-08-25 01:56:11.413148

Issue #25 (Human Review) needs a terminal Post.current_pipeline_stage
distinct from COMPLETED for a run a human explicitly rejected at the
human_review interrupt — COMPLETED implies the post made it all the way
through Publisher/Analytics Collector, which a rejected post never does
(packages/agents/pipeline/graph.py routes human_review straight to END
instead of scheduler when the human's decision is "rejected"). Adds
REJECTED to the pipeline_stage enum, same "add a value, same table"
shape as 75d69ba778a0's agent_type additions.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'c41e72b7ec17'
down_revision: Union[str, None] = 'e7d09d412f48'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGINAL_VALUES = (
    'RESEARCH', 'CREATIVE', 'GENERATION', 'REVIEWER', 'HUMAN_REVIEW',
    'SCHEDULER', 'PUBLISHER', 'ANALYTICS_COLLECTOR', 'COMPLETED',
)


def upgrade() -> None:
    op.execute("ALTER TYPE pipeline_stage ADD VALUE IF NOT EXISTS 'REJECTED'")


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE, so removing REJECTED means
    # rebuilding the enum from scratch (same lossy-on-downgrade tradeoff as
    # 75d69ba778a0's agent_type downgrade) — fails, as expected, if any
    # posts row already uses REJECTED.
    op.execute("ALTER TYPE pipeline_stage RENAME TO pipeline_stage_old")
    new_type = sa.Enum(*_ORIGINAL_VALUES, name='pipeline_stage')
    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE posts "
        "ALTER COLUMN current_pipeline_stage TYPE pipeline_stage "
        "USING current_pipeline_stage::text::pipeline_stage"
    )
    op.execute("DROP TYPE pipeline_stage_old")
