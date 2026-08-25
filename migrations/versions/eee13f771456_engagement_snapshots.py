"""engagement snapshots

Revision ID: eee13f771456
Revises: 16e1fc083897
Create Date: 2026-08-25 02:41:01.925757

Issue #33 needs somewhere to write per-poll engagement metrics for a
published Post, as a true time series — one row per poll, never an
overwrite of a previous row (same "append a log row, never overwrite"
convention agent_runs/post_versions already establish; see
migrations/versions/002_agent_runs.py and
migrations/versions/ec24a3325404_post_body_text_and_post_versions.py).

engagement_snapshots.platform is a plain string, not social_accounts'
social_platform enum (which only defines "linkedin" today) — a post's
*published* platforms (Post.publish_results, Issue #31) can include "x"
even though X has no connectable SocialAccount row yet.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'eee13f771456'
down_revision: Union[str, None] = '16e1fc083897'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'engagement_snapshots',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('platform', sa.String(), nullable=False),
        sa.Column('likes', sa.Integer(), nullable=False),
        sa.Column('comments', sa.Integer(), nullable=False),
        sa.Column('shares', sa.Integer(), nullable=False),
        sa.Column('impressions', sa.Integer(), nullable=False),
        sa.Column('polled_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    # Every poll and every dashboard/report read (#34/#35) filters by
    # post_id (and usually platform) and orders by polled_at — the same
    # access pattern post_versions_post_id_idx already optimizes for.
    op.create_index(
        'engagement_snapshots_post_id_platform_idx',
        'engagement_snapshots',
        ['post_id', 'platform', 'polled_at'],
    )


def downgrade() -> None:
    op.drop_index('engagement_snapshots_post_id_platform_idx', table_name='engagement_snapshots')
    op.drop_table('engagement_snapshots')
