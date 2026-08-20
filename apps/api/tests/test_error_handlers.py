import asyncio
import json

from fastapi.testclient import TestClient
from starlette.requests import Request

from apps.api.middleware.error_handlers import unhandled_exception_handler
from apps.api.main import app

client = TestClient(app)


def test_404_uses_shared_error_shape() -> None:
    response = client.get("/this-route-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["code"] == "not_found"
    assert "message" in body


def test_validation_error_uses_shared_error_shape() -> None:
    # Missing the required "password" field.
    response = client.post("/auth/login", json={"email": "x@x.com"})

    assert response.status_code == 422
    body = response.json()
    assert body["code"] == "validation_error"
    assert isinstance(body["details"], list)
    assert body["details"][0]["loc"][-1] == "password"


def test_unauthorized_uses_shared_error_shape() -> None:
    response = client.get("/brands")

    assert response.status_code == 401
    body = response.json()
    assert body["code"] == "unauthorized"
    assert body["details"] is None


def test_unhandled_exception_handler_returns_generic_500_without_leaking_details() -> None:
    scope = {"type": "http", "method": "GET", "path": "/", "headers": []}
    request = Request(scope)

    response = asyncio.run(
        unhandled_exception_handler(request, ValueError("db password: hunter2"))
    )

    assert response.status_code == 500
    body = json.loads(response.body)
    assert body["code"] == "internal_error"
    assert "hunter2" not in body["message"]
