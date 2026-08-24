"""posts brand_id index

Revision ID: 63bac4f4c66f
Revises: eee13f771456
Create Date: 2026-08-25 02:53:13.750394

Issue #34's analytics aggregation (apps/api/services/analytics_aggregation.py)
computes brand-level engagement aggregates by joining posts to
engagement_snapshots and filtering on posts.brand_id — every one of those
queries starts from "find this brand's posts". posts had no index on
brand_id at all before this (75d69ba778a0_posts_and_pipeline_checkpoints.py
only gave it a primary key + a plain FK constraint on brand_id, which
Postgres does not automatically index), so that join was a sequential scan
of the whole posts table on every analytics request. Paired with
engagement_snapshots_post_id_platform_idx (eee13f771456), this lets
Postgres do brand -> posts -> snapshots entirely through indexes instead of
scanning either table.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '63bac4f4c66f'
down_revision: Union[str, None] = 'eee13f771456'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_index('posts_brand_id_idx', 'posts', ['brand_id'])


def downgrade() -> None:
    op.drop_index('posts_brand_id_idx', table_name='posts')
