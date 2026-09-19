"""onboarding dynamic answers

Revision ID: 04358cec0467
Revises: d017fe5c281d
Create Date: 2026-09-20 00:00:00.000000

Issue #153 — durable storage for Aarav's adaptive, LLM-generated
follow-up questions and the brand's answers to them (the pages that run
after the fixed OnboardingResponse questionnaire). One row per generated
question per page; `question` is the full generated question object
(id/type/title/sub/options) and `answer` is whatever the brand answered
it with, so a later read never needs to regenerate or guess what was
actually asked.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '04358cec0467'
down_revision: Union[str, None] = 'd017fe5c281d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'onboarding_dynamic_answers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('page_index', sa.Integer(), nullable=False),
        sa.Column('question', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('answer', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'onboarding_dynamic_answers_brand_id_idx',
        'onboarding_dynamic_answers',
        ['brand_id'],
    )


def downgrade() -> None:
    op.drop_index('onboarding_dynamic_answers_brand_id_idx', table_name='onboarding_dynamic_answers')
    op.drop_table('onboarding_dynamic_answers')
