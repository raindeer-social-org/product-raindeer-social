from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient


def _build_test_app(allow_origins: list[str]) -> FastAPI:
    # A small standalone app (not the shared production `app`) so this test
    # doesn't depend on real allowed origins or interact with the app's
    # other middleware (rate limiting, logging) — see test_rate_limit.py
    # for the same pattern.
    test_app = FastAPI()
    test_app.add_middleware(
        CORSMiddleware,
        allow_origins=allow_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @test_app.get("/ping")
    def ping() -> dict[str, str]:
        return {"status": "ok"}

    return test_app


def test_preflight_request_from_allowed_origin_gets_cors_header() -> None:
    client = TestClient(_build_test_app(["http://localhost:3000"]))

    response = client.options(
        "/ping",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_actual_request_from_allowed_origin_gets_cors_header() -> None:
    client = TestClient(_build_test_app(["http://localhost:3000"]))

    response = client.get("/ping", headers={"Origin": "http://localhost:3000"})

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"


def test_request_from_disallowed_origin_has_no_cors_header() -> None:
    client = TestClient(_build_test_app(["http://localhost:3000"]))

    response = client.get("/ping", headers={"Origin": "http://evil.example.com"})

    assert response.status_code == 200
    assert "access-control-allow-origin" not in response.headers


def test_cors_origins_setting_parses_comma_separated_list() -> None:
    from apps.api.config import Settings

    settings = Settings(cors_origins="http://localhost:3000, https://app.example.com")

    assert settings.cors_origins_list == [
        "http://localhost:3000",
        "https://app.example.com",
    ]


def test_app_configures_cors_from_settings() -> None:
    # The real app should expose the CORS middleware wired to settings, so
    # a browser session against the configured frontend origin (the
    # default local dev value) doesn't get blocked.
    from apps.api.main import app

    client = TestClient(app)

    response = client.options(
        "/health",
        headers={
            "Origin": "http://localhost:3000",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == "http://localhost:3000"
