"""post body_text and post_versions

Revision ID: ec24a3325404
Revises: 75d69ba778a0
Create Date: 2026-08-24 21:49:15.347638

Issue #21 (Generation Engine) needs somewhere to write its generated copy,
with version history preserved across regenerations. Adds:

  * posts.body_text — a nullable JSONB column holding the *latest*
    generation's copy, keyed by platform (e.g. {"linkedin": "...", "x":
    "..."}), matching creative_brief's per-platform shape.
  * post_versions — an append-only log table, one row per Generation
    Engine run, mirroring agent_runs' "append a log row, never overwrite"
    convention (see migrations/versions/002_agent_runs.py) so an earlier
    generation is never lost when a post is regenerated.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'ec24a3325404'
down_revision: Union[str, None] = '75d69ba778a0'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'posts',
        sa.Column('body_text', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )

    op.create_table(
        'post_versions',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('post_id', sa.UUID(), nullable=False),
        sa.Column('body_text', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('tokens', sa.Integer(), nullable=True),
        sa.Column('cost', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['post_id'], ['posts.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('post_versions_post_id_idx', 'post_versions', ['post_id'])


def downgrade() -> None:
    op.drop_index('post_versions_post_id_idx', table_name='post_versions')
    op.drop_table('post_versions')
    op.drop_column('posts', 'body_text')
