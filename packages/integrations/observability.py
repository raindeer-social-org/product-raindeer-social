import time
from collections.abc import Iterator
from contextlib import contextmanager

from apps.api.config.database import SessionLocal
from apps.api.models.integration_call import IntegrationCall


@contextmanager
def track_integration_call(provider: str, capability: str) -> Iterator[None]:
    """Wraps a single vendor call, logging latency/success/failure to
    integration_calls the same way AgentRun logs agent calls. Logging
    failures never mask the original error, and never prevent it from
    propagating to the caller."""
    start = time.perf_counter()
    error: Exception | None = None
    try:
        yield
    except Exception as exc:
        error = exc
        raise
    finally:
        latency_ms = (time.perf_counter() - start) * 1000
        db = SessionLocal()
        try:
            db.add(
                IntegrationCall(
                    provider=provider,
                    capability=capability,
                    latency_ms=latency_ms,
                    success=error is None,
                    error_message=str(error) if error else None,
                )
            )
            db.commit()
        finally:
            db.close()
