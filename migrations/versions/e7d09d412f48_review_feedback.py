"""review feedback

Revision ID: e7d09d412f48
Revises: ec24a3325404
Create Date: 2026-08-25 01:23:29.364750

Issue #24 (Reviewer Engine) needs somewhere to append its brand-voice/
compliance/platform-fit review of a generated Post. Adds review_feedback,
an append-only evaluation log — one row per review pass, same "append a
row, never overwrite" convention as agent_runs
(migrations/versions/002_agent_runs.py) and post_versions
(migrations/versions/ec24a3325404_post_body_text_and_post_versions.py).

`source` distinguishes who produced a given row: the Reviewer Engine only
ever writes 'ai_reviewer' rows, but #25's human-review UI will append
'human' rows onto this same table, so a Post's review history reads as
one ordered log rather than two things a caller has to reconcile.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'e7d09d412f48'
down_revision: Union[str, None] = 'ec24a3325404'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'review_feedback',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('source', sa.Enum('AI_REVIEWER', 'HUMAN', name='review_source'), nullable=False),
        sa.Column('score', sa.Float(), nullable=False),
        sa.Column('verdict', sa.Enum('APPROVE', 'REVISE', 'REJECT', name='review_verdict'), nullable=False),
        sa.Column('comments', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('review_feedback_post_id_idx', 'review_feedback', ['post_id'])


def downgrade() -> None:
    op.drop_index('review_feedback_post_id_idx', table_name='review_feedback')
    op.drop_table('review_feedback')
    # drop_table doesn't drop the enum types it implicitly created —
    # without this, re-running upgrade() after a downgrade fails with
    # DuplicateObject (same gotcha as 001_core_schema.py's user_role).
    sa.Enum(name='review_verdict').drop(op.get_bind(), checkfirst=True)
    sa.Enum(name='review_source').drop(op.get_bind(), checkfirst=True)
