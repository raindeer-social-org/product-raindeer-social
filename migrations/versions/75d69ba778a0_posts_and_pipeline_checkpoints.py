"""posts and pipeline checkpoints

Revision ID: 75d69ba778a0
Revises: b080bafe185d
Create Date: 2026-08-24 21:16:11.745069

Adds Issue #18's Post model plus the tables LangGraph's PostgresSaver
needs for durable checkpoint persistence (checkpoints / checkpoint_blobs /
checkpoint_writes / checkpoint_migrations). Schema for those four tables
matches exactly what `PostgresSaver.setup()` would create at runtime
(langgraph.checkpoint.postgres, package langgraph-checkpoint-postgres) —
see packages/agents/pipeline/checkpointer.py for why this repo creates
them via Alembic instead of calling `.setup()` at runtime. The
concurrently-built indexes `.setup()` uses are created as plain
(non-CONCURRENT) indexes here instead, since these tables are empty at
migration time and CREATE INDEX CONCURRENTLY can't run inside Alembic's
migration transaction. `checkpoint_migrations` is seeded with the same
rows `.setup()` would leave behind, so nothing ever tries to re-run
those migrations against this schema.
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '75d69ba778a0'
down_revision: Union[str, None] = 'b080bafe185d'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Number of PostgresSaver.MIGRATIONS entries as of langgraph-checkpoint-postgres
# 3.1.2 — kept in sync with checkpointer.py's docstring. Seeded into
# checkpoint_migrations below so PostgresSaver.setup() is a no-op if it's
# ever invoked against this schema.
_CHECKPOINT_MIGRATION_COUNT = 10

_NEW_AGENT_TYPES = ("HUMAN_REVIEW", "SCHEDULER", "PUBLISHER", "ANALYTICS_COLLECTOR")
_ORIGINAL_AGENT_TYPES = ("ONBOARDING", "RESEARCH", "CREATIVE", "GENERATION", "REVIEWER")


def upgrade() -> None:
    # --- agent_type: add the stub pipeline stages introduced by this issue ---
    for value in _NEW_AGENT_TYPES:
        op.execute(f"ALTER TYPE agent_type ADD VALUE IF NOT EXISTS '{value}'")

    # --- posts ---
    op.create_table(
        'posts',
        sa.Column('id', sa.UUID(), nullable=False),
        sa.Column('brand_id', sa.UUID(), nullable=False),
        sa.Column('calendar_event_id', sa.UUID(), nullable=True),
        sa.Column(
            'current_pipeline_stage',
            sa.Enum(
                'RESEARCH', 'CREATIVE', 'GENERATION', 'REVIEWER', 'HUMAN_REVIEW',
                'SCHEDULER', 'PUBLISHER', 'ANALYTICS_COLLECTOR', 'COMPLETED',
                name='pipeline_stage',
            ),
            nullable=False,
        ),
        sa.Column('created_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), server_default=sa.text('now()'), nullable=False),
        sa.ForeignKeyConstraint(['brand_id'], ['brands.id']),
        sa.ForeignKeyConstraint(['calendar_event_id'], ['content_calendar_events.id']),
        sa.PrimaryKeyConstraint('id'),
    )

    # --- LangGraph Postgres checkpoint tables (PostgresSaver schema) ---
    op.create_table(
        'checkpoint_migrations',
        sa.Column('v', sa.Integer(), nullable=False),
        sa.PrimaryKeyConstraint('v'),
    )

    op.create_table(
        'checkpoints',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('checkpoint_id', sa.Text(), nullable=False),
        sa.Column('parent_checkpoint_id', sa.Text(), nullable=True),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('checkpoint', postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column('metadata', postgresql.JSONB(astext_type=sa.Text()), nullable=False, server_default=sa.text("'{}'")),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id'),
    )
    op.create_index('checkpoints_thread_id_idx', 'checkpoints', ['thread_id'])

    op.create_table(
        'checkpoint_blobs',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('version', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=False),
        sa.Column('blob', sa.LargeBinary(), nullable=True),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'channel', 'version'),
    )
    op.create_index('checkpoint_blobs_thread_id_idx', 'checkpoint_blobs', ['thread_id'])

    op.create_table(
        'checkpoint_writes',
        sa.Column('thread_id', sa.Text(), nullable=False),
        sa.Column('checkpoint_ns', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.Column('checkpoint_id', sa.Text(), nullable=False),
        sa.Column('task_id', sa.Text(), nullable=False),
        sa.Column('idx', sa.Integer(), nullable=False),
        sa.Column('channel', sa.Text(), nullable=False),
        sa.Column('type', sa.Text(), nullable=True),
        sa.Column('blob', sa.LargeBinary(), nullable=False),
        sa.Column('task_path', sa.Text(), nullable=False, server_default=sa.text("''")),
        sa.PrimaryKeyConstraint('thread_id', 'checkpoint_ns', 'checkpoint_id', 'task_id', 'idx'),
    )
    op.create_index('checkpoint_writes_thread_id_idx', 'checkpoint_writes', ['thread_id'])

    op.bulk_insert(
        sa.table('checkpoint_migrations', sa.column('v', sa.Integer())),
        [{'v': v} for v in range(_CHECKPOINT_MIGRATION_COUNT)],
    )


def downgrade() -> None:
    op.drop_table('checkpoint_writes')
    op.drop_table('checkpoint_blobs')
    op.drop_table('checkpoints')
    op.drop_table('checkpoint_migrations')

    op.drop_table('posts')
    sa.Enum(name='pipeline_stage').drop(op.get_bind(), checkfirst=True)

    # Postgres has no ALTER TYPE ... DROP VALUE, so removing the four
    # stub-stage agent_type values means rebuilding the enum from scratch.
    # (Fails, as expected, if any row already uses one of those values —
    # same lossy-on-downgrade tradeoff every enum migration in this repo
    # makes.)
    op.execute("ALTER TYPE agent_type RENAME TO agent_type_old")
    new_type = sa.Enum(*_ORIGINAL_AGENT_TYPES, name='agent_type')
    new_type.create(op.get_bind())
    op.execute(
        "ALTER TABLE agent_runs "
        "ALTER COLUMN agent_type TYPE agent_type USING agent_type::text::agent_type"
    )
    op.execute("DROP TYPE agent_type_old")
