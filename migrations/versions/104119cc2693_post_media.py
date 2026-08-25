"""post media

Revision ID: 104119cc2693
Revises: ec24a3325404
Create Date: 2026-08-24 21:58:19.362081

Issue #22 (fal.ai image-generation adapter) needs somewhere to link the
Generation Engine's generated media onto the Post it belongs to. Adds:

  * posts.media — a nullable JSONB column holding a list of media
    references produced by the *latest* generation run that actually
    produced media (e.g. [{"platform": "linkedin", "format": "image",
    "url": "..."}]), mirroring posts.body_text's "written by the
    Generation Engine" convention (see migrations/versions/
    ec24a3325404_post_body_text_and_post_versions.py) but, unlike
    body_text, only touched when a run produces new media rather than
    unconditionally overwritten every run.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '104119cc2693'
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
