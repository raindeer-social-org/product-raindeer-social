"""reports table and weekly_report agent type

Revision ID: 0d2a5fb92eb0
Revises: c4d732c135f1
Create Date: 2026-08-25 12:11:45.550322

Issue #35: the weekly AI-generated report per brand
(packages/agents/reporting/weekly_report.py). Adds the `reports` table
(apps/api/models/report.py) plus a new WEEKLY_REPORT value on the
`agent_type` enum, since generation is logged as an AgentRun the same way
every other LLM-backed stage in this repo is (see AgentRun.agent_type in
apps/api/models/agent_run.py) — same "add a value, same table" shape as
75d69ba778a0's original agent_type additions and c41e72b7ec17's REJECTED
pipeline_stage addition.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '0d2a5fb92eb0'
down_revision: Union[str, None] = 'c4d732c135f1'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Full agent_type value set immediately before this migration (original
# five from 002_agent_runs.py plus the four stub stages 75d69ba778a0
# added) — needed to rebuild the enum on downgrade, same lossy-on-
# downgrade tradeoff every enum migration in this repo makes.
_PRE_EXISTING_AGENT_TYPES = (
    'ONBOARDING', 'RESEARCH', 'CREATIVE', 'GENERATION', 'REVIEWER',
    'HUMAN_REVIEW', 'SCHEDULER', 'PUBLISHER', 'ANALYTICS_COLLECTOR',
)


def upgrade() -> None:
    # --- agent_type: add the new weekly-report stage ---
    op.execute("ALTER TYPE agent_type ADD VALUE IF NOT EXISTS 'WEEKLY_REPORT'")

    # --- reports ---
    op.create_table(
        'reports',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('period_start', sa.DateTime(timezone=True), nullable=False),
        sa.Column('period_end', sa.DateTime(timezone=True), nullable=False),
        sa.Column('summary', sa.Text(), nullable=False),
        sa.Column('recommendations', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metrics', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('model', sa.String(), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id']),
        sa.PrimaryKeyConstraint('id'),
    )
    op.create_index('reports_brand_id_idx', 'reports', ['brand_id'])


def downgrade() -> None:
    op.drop_index('reports_brand_id_idx', table_name='reports')
    op.drop_table('reports')

    # Postgres has no ALTER TYPE ... DROP VALUE, so removing WEEKLY_REPORT
    # means rebuilding the enum from scratch — fails, as expected, if any
    # agent_runs row already uses it.
    op.execute("ALTER TYPE agent_type RENAME TO agent_type_old")
    new_type = sa.Enum(*_PRE_EXISTING_AGENT_TYPES, name='agent_type')
    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE agent_runs "
        "ALTER COLUMN agent_type TYPE agent_type USING agent_type::text::agent_type"
    )
    op.execute("DROP TYPE agent_type_old")
