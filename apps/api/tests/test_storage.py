from unittest.mock import MagicMock, patch

from apps.api.models import IntegrationCall
from packages.integrations.storage.supabase_provider import SupabaseStorageProvider


def _provider() -> SupabaseStorageProvider:
    return SupabaseStorageProvider(
        base_url="https://project.supabase.co",
        service_key="test-key",
        bucket="brand-assets",
    )


def _ok_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


def test_upload_returns_public_url(db_session) -> None:
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        url = _provider().upload("org1/brand1/logo", b"fake-image-bytes", "image/png")

    assert url == "https://project.supabase.co/storage/v1/object/public/brand-assets/org1/brand1/logo"
    call_kwargs = mock_post.call_args.kwargs
    assert call_kwargs["headers"]["Authorization"] == "Bearer test-key"
    assert call_kwargs["headers"]["Content-Type"] == "image/png"
    assert call_kwargs["headers"]["x-upsert"] == "true"
    assert call_kwargs["content"] == b"fake-image-bytes"


def test_upload_uses_correct_endpoint(db_session) -> None:
    with patch("httpx.post", return_value=_ok_response()) as mock_post:
        _provider().upload("org1/brand1/logo", b"data", "image/png")

    url_called = mock_post.call_args.args[0]
    assert url_called == "https://project.supabase.co/storage/v1/object/brand-assets/org1/brand1/logo"


def test_delete_calls_correct_endpoint(db_session) -> None:
    with patch("httpx.delete", return_value=_ok_response()) as mock_delete:
        _provider().delete("org1/brand1/logo")

    url_called = mock_delete.call_args.args[0]
    assert url_called == "https://project.supabase.co/storage/v1/object/brand-assets/org1/brand1/logo"
    assert mock_delete.call_args.kwargs["headers"]["Authorization"] == "Bearer test-key"


def test_upload_logs_integration_call(db_session) -> None:
    with patch("httpx.post", return_value=_ok_response()):
        _provider().upload("org1/brand1/logo", b"data", "image/png")

    logged = (
        db_session.query(IntegrationCall)
        .filter_by(provider="supabase", capability="storage")
        .order_by(IntegrationCall.created_at.desc())
        .first()
    )
    assert logged is not None
    assert logged.success is True


def test_get_url_format() -> None:
    url = _provider().get_url("org1/brand1/logo")
    assert url == "https://project.supabase.co/storage/v1/object/public/brand-assets/org1/brand1/logo"
