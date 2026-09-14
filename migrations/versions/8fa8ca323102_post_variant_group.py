"""post variant group

Revision ID: 8fa8ca323102
Revises: 5b29b584c4fa
Create Date: 2026-08-27 00:35:59.492114

Issue #106 (Kavi batch generation) lets the Generation Engine
(packages/agents/pipeline/nodes/generation_engine.py) optionally produce
several distinct post variants (copy + image each) from a single creative
brief in one run, instead of exactly one Post per pipeline run. Each
variant is its own Post row (own body_text/media/PostVersion history, so
existing single-post assumptions elsewhere in the codebase keep holding),
tied to its siblings from the same generation run via a shared, nullable
"variant group" id — nothing like this exists yet (this repo's only
per-post grouping so far is calendar_event_id, which is a 1:1 link to a
calendar slot, not a sibling-grouping concept). Adds:

  * posts.variant_group_id — nullable UUID, shared by every Post produced
    by the same batch generation run. NULL for every Post produced by the
    existing (default, unchanged) single-post generation path, since those
    have no siblings to group with.
  * posts.variant_index — nullable integer, this Post's 1-based position
    within its variant group (1 for the original post that triggered the
    run, 2..N for the additional sibling Posts batch mode creates). NULL
    alongside variant_group_id for non-batch Posts.

An index on variant_group_id supports the natural "fetch every variant in
this batch so a human can pick/edit one" query a future review-queue
endpoint would run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '8fa8ca323102'
down_revision: Union[str, None] = '5b29b584c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('posts', sa.Column('variant_group_id', sa.UUID(), nullable=True))
    op.add_column('posts', sa.Column('variant_index', sa.Integer(), nullable=True))
    op.create_index('posts_variant_group_id_idx', 'posts', ['variant_group_id'])


def downgrade() -> None:
    op.drop_index('posts_variant_group_id_idx', table_name='posts')
    op.drop_column('posts', 'variant_index')
    op.drop_column('posts', 'variant_group_id')
