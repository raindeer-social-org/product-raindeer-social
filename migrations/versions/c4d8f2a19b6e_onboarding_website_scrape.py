"""onboarding website scrape

Revision ID: c4d8f2a19b6e
Revises: d017fe5c281d
Create Date: 2026-09-20 00:00:00.000000

Issue #152 — Aarav's "confirm your website" onboarding step previously
only ran a Tavily *search* for public signals about the brand, never
actually fetched the brand's own site. This adds somewhere for a real
scrape's output to land: onboarding_research.website_summary (an LLM
distillation of the scraped page text — never the raw scrape, see
packages/agents/onboarding/research_step.py::run_website_scrape's
docstring), website_logo_url (our own StorageProvider-hosted copy of
whatever logo/favicon the scrape found), and website_colors (a small
dominant-color palette extracted from that logo).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'c4d8f2a19b6e'
down_revision: Union[str, None] = 'd017fe5c281d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column('onboarding_research', sa.Column('website_summary', sa.String(), nullable=True))
    op.add_column('onboarding_research', sa.Column('website_logo_url', sa.String(), nullable=True))
    op.add_column(
        'onboarding_research',
        sa.Column('website_colors', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )


def downgrade() -> None:
    op.drop_column('onboarding_research', 'website_colors')
    op.drop_column('onboarding_research', 'website_logo_url')
    op.drop_column('onboarding_research', 'website_summary')
