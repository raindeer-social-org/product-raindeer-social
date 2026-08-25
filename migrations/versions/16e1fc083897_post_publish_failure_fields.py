"""post publish failure fields

Revision ID: 16e1fc083897
Revises: c41e72b7ec17
Create Date: 2026-08-25 02:28:13.513657

Issue #31 (publish queue) needs somewhere to durably record a real
publish attempt's outcome:

  * posts.publish_results — a nullable JSONB column, per-platform outcome
    of the most recent publish attempt (e.g. {"linkedin": {"status":
    "published", "platform_post_id": "...", "platform_post_url": "..."},
    "x": {"status": "failed", "error": "..."}}). Read back on every retry
    so an already-published platform is never re-published just because a
    sibling platform's attempt failed.
  * posts.publish_error — a nullable text column, a single human-readable
    summary of the most recent failure (across whichever platform(s)
    failed), so a caller never has to reach into publish_results just to
    show "why did this fail". Cleared back to NULL on a fully successful
    publish.

Also adds FAILED to the pipeline_stage enum — the terminal
current_pipeline_stage a Post lands on when the publish queue's retries
are genuinely exhausted, distinct from COMPLETED (which the pipeline
graph already reaches once `publisher` hands the post off to the async
publish queue, before the real publish outcome is known) — same "add a
value, same table" shape as c41e72b7ec17's REJECTED addition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '16e1fc083897'
down_revision: Union[str, None] = 'c41e72b7ec17'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_ORIGINAL_VALUES = (
    'RESEARCH', 'CREATIVE', 'GENERATION', 'REVIEWER', 'HUMAN_REVIEW',
    'SCHEDULER', 'PUBLISHER', 'ANALYTICS_COLLECTOR', 'COMPLETED', 'REJECTED',
)


def upgrade() -> None:
    op.execute("ALTER TYPE pipeline_stage ADD VALUE IF NOT EXISTS 'FAILED'")

    op.add_column(
        'posts',
        sa.Column('publish_results', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column(
        'posts',
        sa.Column('publish_error', sa.String(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('posts', 'publish_error')
    op.drop_column('posts', 'publish_results')

    # Postgres has no ALTER TYPE ... DROP VALUE, so removing FAILED means
    # rebuilding the enum from scratch (same lossy-on-downgrade tradeoff as
    # c41e72b7ec17's REJECTED downgrade) — fails, as expected, if any
    # posts row already uses FAILED.
    op.execute("ALTER TYPE pipeline_stage RENAME TO pipeline_stage_old")
    new_type = sa.Enum(*_ORIGINAL_VALUES, name='pipeline_stage')
    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE posts "
        "ALTER COLUMN current_pipeline_stage TYPE pipeline_stage "
        "USING current_pipeline_stage::text::pipeline_stage"
    )
    op.execute("DROP TYPE pipeline_stage_old")
