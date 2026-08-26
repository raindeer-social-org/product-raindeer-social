import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor

import httpx
import uvicorn
from fastapi import FastAPI
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token
from apps.api.middleware.rate_limit import RateLimitMiddleware


def _build_test_app(limit: int) -> FastAPI:
    # A small standalone app, not the shared production `app` — using a
    # low limit against the real app would make this test interfere with
    # every other test hitting /auth or /brands within the same 60s
    # window. The per-org key (via a real JWT with a fresh random org_id
    # below) keeps this fully isolated regardless.
    test_app = FastAPI()
    test_app.add_middleware(RateLimitMiddleware, limit=limit, path_prefixes=("/",))

    @test_app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    return test_app


def test_requests_within_limit_succeed() -> None:
    client = TestClient(_build_test_app(limit=5))
    token = create_access_token(user_id="u1", org_id="org-within-limit", role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(5):
        response = client.get("/ping", headers=headers)
        assert response.status_code == 200


def test_request_past_limit_returns_429_with_retry_after() -> None:
    client = TestClient(_build_test_app(limit=2))
    token = create_access_token(user_id="u1", org_id="org-past-limit", role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    for _ in range(2):
        assert client.get("/ping", headers=headers).status_code == 200

    response = client.get("/ping", headers=headers)

    assert response.status_code == 429
    assert "Retry-After" in response.headers
    assert int(response.headers["Retry-After"]) > 0
    assert response.json()["code"] == "rate_limited"


def test_rate_limit_is_scoped_per_org() -> None:
    client = TestClient(_build_test_app(limit=1))
    token_a = create_access_token(user_id="u1", org_id="org-a-scoped", role="viewer")
    token_b = create_access_token(user_id="u2", org_id="org-b-scoped", role="viewer")

    assert client.get("/ping", headers={"Authorization": f"Bearer {token_a}"}).status_code == 200
    # Org A is now at its limit — org B should be unaffected.
    assert client.get("/ping", headers={"Authorization": f"Bearer {token_b}"}).status_code == 200
    assert client.get("/ping", headers={"Authorization": f"Bearer {token_a}"}).status_code == 429


# ---------------------------------------------------------------------------
# Issue #37 hardening pass: does the limiter hold under genuine concurrency,
# not just sequential requests?
#
# TestClient (above) is unsuitable for this: it dispatches every request
# through a single anyio blocking-portal event loop
# (starlette.testclient.TestClient._portal_factory), and
# RateLimitMiddleware.dispatch calls the *synchronous* redis-py client
# (self.redis.incr(...)) without an executor — a blocking call with no
# `await` inside it, so the event loop cannot switch to another in-flight
# request while it runs. Multiple Python threads calling a shared
# TestClient "concurrently" would still have every request's redis.incr()
# execute start-to-finish without interleaving, which would make even a
# genuinely broken non-atomic counter (`get` then `set` instead of `incr`)
# pass. That would test nothing.
#
# So this spins up the real ASGI app behind an actual uvicorn server on a
# real socket and fires real concurrent HTTP requests at it from a
# ThreadPoolExecutor + a threading.Barrier to align their start — genuine
# OS-thread-level concurrency, with real socket I/O (which releases the
# GIL), against a middleware instance backed by the real local Redis.
# Redis's INCR is atomic server-side regardless of how many clients race
# it, so this is expected to hold exactly at the configured limit; the
# test exists to catch a regression (e.g. someone "simplifying" the
# middleware to a get/compare/set) rather than a currently-suspected bug.
# ---------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class _LiveServer:
    """Runs a FastAPI app behind a real uvicorn server in a background
    thread, on a real socket — needed for genuine concurrent-request tests
    (see module docstring above); TestClient's single-event-loop dispatch
    can't produce real concurrency here."""

    def __init__(self, app: FastAPI) -> None:
        self.port = _free_port()
        config = uvicorn.Config(app, host="127.0.0.1", port=self.port, log_level="warning")
        self.server = uvicorn.Server(config)
        self._thread = threading.Thread(target=self.server.run, daemon=True)

    @property
    def base_url(self) -> str:
        return f"http://127.0.0.1:{self.port}"

    def __enter__(self) -> "_LiveServer":
        self._thread.start()
        deadline = time.monotonic() + 10
        while not self.server.started:
            if time.monotonic() > deadline:
                raise RuntimeError("uvicorn server did not start in time")
            time.sleep(0.02)
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.server.should_exit = True
        self._thread.join(timeout=10)


def test_concurrent_requests_hold_exactly_at_the_limit() -> None:
    limit = 20
    concurrency = 60  # 3x the limit, all fired at once
    app = _build_test_app(limit=limit)
    token = create_access_token(user_id="u1", org_id=f"org-concurrent-{uuid.uuid4()}", role="viewer")
    headers = {"Authorization": f"Bearer {token}"}

    with _LiveServer(app) as live:
        barrier = threading.Barrier(concurrency)

        def _fire(_: int) -> int:
            with httpx.Client(base_url=live.base_url) as http_client:
                barrier.wait(timeout=10)  # line every thread up before any request goes out
                return http_client.get("/ping", headers=headers).status_code

        with ThreadPoolExecutor(max_workers=concurrency) as pool:
            statuses = list(pool.map(_fire, range(concurrency)))

    ok_count = sum(1 for s in statuses if s == 200)
    limited_count = sum(1 for s in statuses if s == 429)

    assert ok_count + limited_count == concurrency, f"unexpected status codes: {statuses}"
    # The core assertion: concurrency must not let more than `limit` through
    # (no double-counting/lost-increment race) and must not block more than
    # necessary either (no over-counting race that starves legitimate
    # requests) — exactly `limit` succeed, no more, no less.
    assert ok_count == limit, f"expected exactly {limit} successes under concurrency, got {ok_count}"
    assert limited_count == concurrency - limit
