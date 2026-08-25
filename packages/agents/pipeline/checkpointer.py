"""Postgres-backed checkpoint persistence for the per-post pipeline graph.

LangGraph 1.x ships its Postgres checkpoint saver as the separate
``langgraph-checkpoint-postgres`` package (``langgraph.checkpoint.postgres``),
not bundled with the core ``langgraph`` distribution — see
apps/api/requirements.txt. This module wraps that saver rather than
hand-rolling checkpoint storage, so the pipeline graph gets durable,
resumable interrupts (Issue #18) for free.

Schema ownership: PostgresSaver normally creates its own tables at runtime
via ``PostgresSaver.setup()``. This repo instead manages all schema through
Alembic (see migrations/versions for the checkpoints/checkpoint_blobs/
checkpoint_writes/checkpoint_migrations tables), matching how every other
table here is created — so this module deliberately never calls
``.setup()``. The migration seeds ``checkpoint_migrations`` with the same
rows ``.setup()`` would have written, so the schema PostgresSaver expects
already exists by the time any pipeline code runs.
"""

from collections.abc import Iterator
from contextlib import contextmanager

from langgraph.checkpoint.postgres import PostgresSaver

from apps.api.config import get_settings


@contextmanager
def get_postgres_checkpointer(database_url: str | None = None) -> Iterator[PostgresSaver]:
    """Yields a PostgresSaver bound to a fresh psycopg connection against
    this repo's Postgres database (``Settings.database_url`` by default).

    Callers are expected to use this as a short-lived context manager per
    pipeline invocation (mirrors apps/api/config/database.py's get_db()
    pattern) rather than holding one connection open for the process
    lifetime — a paused pipeline run doesn't need a live connection while
    it's waiting on a human, only when it's actually being advanced."""
    conn_string = database_url or get_settings().database_url
    with PostgresSaver.from_conn_string(conn_string) as checkpointer:
        yield checkpointer
