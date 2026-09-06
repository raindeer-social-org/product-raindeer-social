"""onboarding voice answers, assets, and deeper questionnaire fields

Revision ID: a3f7c9e1d204
Revises: 5b29b584c4fa
Create Date: 2026-09-06 16:05:00.000000

Issue #144 — Aarav's onboarding interview previously had a "voice"
question that recorded nothing ("Recording is illustrative only — no
audio is captured") and 4 upload slots wired to nothing. This adds
somewhere for both to actually land:

  * onboarding_voice_answers — one row per recorded take (raw audio via
    StorageProvider + its Whisper transcript); never overwritten, same
    "append, don't overwrite" convention post_versions/agent_runs use.
  * onboarding_assets — one row per (brand, slot) upload; a re-upload to
    an already-filled slot replaces that slot's row (unique constraint),
    same "one current value per slot" model as Brand.logo_url.
  * onboarding_responses gains mission/content_dos_donts/posting_cadence
    — optional deeper-questionnaire fields feeding
    packages/agents/onboarding/prompts.py's synthesis prompt, not added
    to REQUIRED_FIELDS so existing onboarding flows aren't blocked.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = 'a3f7c9e1d204'
down_revision: Union[str, None] = '5b29b584c4fa'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        'onboarding_voice_answers',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('question_id', sa.String(), nullable=False),
        sa.Column('transcript', sa.String(), nullable=False),
        sa.Column('audio_url', sa.String(), nullable=False),
        sa.Column('language', sa.String(), nullable=True),
        sa.Column('duration_seconds', sa.Float(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index(
        'onboarding_voice_answers_brand_id_idx',
        'onboarding_voice_answers',
        ['brand_id'],
    )

    op.create_table(
        'onboarding_assets',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('slot', sa.String(), nullable=False),
        sa.Column('url', sa.String(), nullable=False),
        sa.Column('filename', sa.String(), nullable=False),
        sa.Column('content_type', sa.String(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id']),
        sa.PrimaryKeyConstraint('id'),
        sa.UniqueConstraint('brand_id', 'slot', name='uq_onboarding_asset_brand_slot'),
    )

    op.add_column('onboarding_responses', sa.Column('mission', sa.String(), nullable=True))
    op.add_column(
        'onboarding_responses',
        sa.Column('content_dos_donts', postgresql.JSONB(astext_type=sa.Text()), nullable=True),
    )
    op.add_column('onboarding_responses', sa.Column('posting_cadence', sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column('onboarding_responses', 'posting_cadence')
    op.drop_column('onboarding_responses', 'content_dos_donts')
    op.drop_column('onboarding_responses', 'mission')

    op.drop_table('onboarding_assets')

    op.drop_index('onboarding_voice_answers_brand_id_idx', table_name='onboarding_voice_answers')
    op.drop_table('onboarding_voice_answers')
