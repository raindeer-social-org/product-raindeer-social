"""add website social links to onboarding research

Revision ID: 0cb88eee70c5
Revises: 09d2ace33584
Create Date: 2026-09-22 10:28:48.509630

Adds onboarding_research.website_social_links — social profile links
(instagram/linkedin/x/...) found on the brand's own scraped page (footer/
header icons, "follow us" sections), surfaced as real signal rather than
scraped further (see packages/integrations/webscrape's
_find_social_links docstring for why not).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0cb88eee70c5'
down_revision: Union[str, None] = '09d2ace33584'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        'onboarding_research',
        sa.Column('website_social_links', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('onboarding_research', 'website_social_links')
