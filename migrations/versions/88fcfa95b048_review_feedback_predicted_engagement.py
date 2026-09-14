"""review feedback predicted engagement

Revision ID: 88fcfa95b048
Revises: 5b29b584c4fa
Create Date: 2026-08-27 00:00:00.000000

Issue #107 — the Reviewer Engine gains a predicted-engagement pass
alongside its existing brand-alignment/compliance/platform-fit score.
Adds two nullable columns to review_feedback (Issue #24's
migrations/versions/e7d09d412f48_review_feedback.py): a 0-100
predicted_engagement_score and a short natural-language
predicted_engagement_reasoning string. Nullable because only
source=ai_reviewer rows populate them; source=human rows (#25's
approve/reject) never predict engagement.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '88fcfa95b048'
down_revision: Union[str, None] = '5b29b584c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('review_feedback', sa.Column('predicted_engagement_score', sa.Float(), nullable=True))
    op.add_column('review_feedback', sa.Column('predicted_engagement_reasoning', sa.Text(), nullable=True))


def downgrade() -> None:
    op.drop_column('review_feedback', 'predicted_engagement_reasoning')
    op.drop_column('review_feedback', 'predicted_engagement_score')
