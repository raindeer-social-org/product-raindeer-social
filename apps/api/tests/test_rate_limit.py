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
