"""post media

Revision ID: 3f507aa255e5
Revises: ec24a3325404
Create Date: 2026-08-24 22:00:03.780364

Issue #23 (Generation Engine's video/carousel branch) needs somewhere to
link generated media onto the Post it belongs to. Adds:

  * posts.media — a nullable JSONB column, a dict keyed by platform (same
    per-platform shape as posts.body_text, added in ec24a3325404), where
    each value is a *list* of media reference dicts (e.g. [{"url": ...,
    "status": "generated", "format": "short_video"}]) rather than a plain
    string, since a carousel is multiple media items for one platform.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '3f507aa255e5'
down_revision: Union[str, None] = 'ec24a3325404'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'posts',
        sa.Column('media', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('posts', 'media')
