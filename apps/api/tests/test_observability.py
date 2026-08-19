import json
import logging
from unittest.mock import patch

from fastapi.testclient import TestClient

from apps.api.main import app
from apps.api.middleware.logging import logger
from apps.api.observability import init_sentry

client = TestClient(app)


def test_request_logging_emits_structured_json() -> None:
    # `logger` runs with propagate=False (by design, to avoid duplicate
    # output via the root logger's default handler in production), which
    # means pytest's caplog — which captures at the root logger — can't see
    # it. Attach a handler directly to this named logger instead.
    records: list[logging.LogRecord] = []
    collector = logging.Handler()
    collector.emit = records.append  # type: ignore[method-assign]
    logger.addHandler(collector)

    try:
        response = client.get("/health")
    finally:
        logger.removeHandler(collector)

    assert response.status_code == 200
    assert len(records) == 1

    payload = json.loads(logger.handlers[0].format(records[0]))
    assert payload["method"] == "GET"
    assert payload["path"] == "/health"
    assert payload["status_code"] == 200
    assert isinstance(payload["duration_ms"], (int, float))


def test_init_sentry_noop_without_dsn() -> None:
    with patch("sentry_sdk.init") as mock_init:
        init_sentry(dsn=None, environment="test")
    mock_init.assert_not_called()


def test_init_sentry_called_with_dsn() -> None:
    with patch("sentry_sdk.init") as mock_init:
        init_sentry(dsn="https://example@sentry.io/1", environment="test")
    mock_init.assert_called_once_with(
        dsn="https://example@sentry.io/1", environment="test"
    )
