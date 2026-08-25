from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfReader
import io

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, Organization, User, UserRole
from apps.api.services.brand_report_pdf import render_brand_report_pdf

client = TestClient(app)

uses_test_session = pytest.mark.usefixtures("override_get_db")

REPORT = {
    "voice_and_tone": "Playful and direct.",
    "audience": "Gen Z consumers who value sustainability.",
    "product_catalog_summary": "A line of eco-friendly widgets.",
    "competitive_positioning": "Positioned as the premium, sustainable alternative to Widgetron.",
}

UPDATED_REPORT = {
    "voice_and_tone": "Formal and understated.",
    "audience": "Gen Z consumers who value sustainability.",
    "product_catalog_summary": "A line of eco-friendly widgets, now with a new lineup.",
    "competitive_positioning": "Positioned as the premium, sustainable alternative to Widgetron.",
}


def _pdf_text(pdf_bytes: bytes) -> str:
    reader = PdfReader(io.BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def _create_org_and_user(db_session, role: UserRole, email: str) -> tuple[Organization, User]:
    org = Organization(name=f"Org for {email}")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=email,
        password_hash=hash_password("test-password"),
        role=role,
    )
    db_session.add(user)
    db_session.flush()
    return org, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


def _ok_storage_response() -> MagicMock:
    response = MagicMock()
    response.raise_for_status.return_value = None
    return response


# --- render_brand_report_pdf (service-level) ---------------------------


def test_render_pdf_includes_all_sections() -> None:
    pdf_bytes = render_brand_report_pdf("Acme Widgets", REPORT)

    assert pdf_bytes.startswith(b"%PDF")
    text = _pdf_text(pdf_bytes)
    assert "Acme Widgets" in text
    for value in REPORT.values():
        assert value in text
    # section headings rendered too, not just body text
    assert "Voice And Tone" in text
    assert "Audience" in text
    assert "Product Catalog Summary" in text
    assert "Competitive Positioning" in text


def test_render_pdf_raises_on_empty_report() -> None:
    with pytest.raises(ValueError):
        render_brand_report_pdf("Acme Widgets", {})


def test_render_pdf_raises_on_missing_required_section() -> None:
    incomplete = {"voice_and_tone": "Playful"}
    with pytest.raises(ValueError):
        render_brand_report_pdf("Acme Widgets", incomplete)


def test_render_pdf_includes_extra_sections_beyond_required() -> None:
    report_with_extra = {**REPORT, "goals": "Grow LinkedIn engagement 2x this quarter."}
    pdf_bytes = render_brand_report_pdf("Acme Widgets", report_with_extra)

    text = _pdf_text(pdf_bytes)
    assert "Grow LinkedIn engagement 2x this quarter." in text
    assert "Goals" in text


# --- export endpoint -----------------------------------------------------


@uses_test_session
def test_editor_can_export_brand_report(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor@acme.test")
    headers = _auth_headers(user)
    created = client.post(
        "/brands", json={"name": "Acme Widgets"}, headers=headers
    ).json()

    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()

    with patch("httpx.post", return_value=_ok_storage_response()) as mock_post:
        response = client.post(
            f"/brands/{created['id']}/report/export", headers=headers
        )

    assert response.status_code == 200
    body = response.json()
    assert "url" in body and body["url"]
    assert "generated_at" in body
    uploaded_path = mock_post.call_args.args[0]
    assert f"{user.organization_id}/{created['id']}/report-" in uploaded_path
    uploaded_content = mock_post.call_args.kwargs["content"]
    assert uploaded_content.startswith(b"%PDF")


@uses_test_session
def test_viewer_cannot_export_brand_report(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor2@acme.test")
    headers = _auth_headers(user)
    created = client.post("/brands", json={"name": "Name"}, headers=headers).json()

    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()

    _org2, viewer = _create_org_and_user(db_session, UserRole.VIEWER, "pdf-viewer@acme.test")
    viewer.organization_id = user.organization_id
    db_session.flush()

    response = client.post(
        f"/brands/{created['id']}/report/export", headers=_auth_headers(viewer)
    )
    assert response.status_code == 403


@uses_test_session
def test_export_without_brand_report_returns_400(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor3@acme.test")
    headers = _auth_headers(user)
    created = client.post("/brands", json={"name": "No Report Yet"}, headers=headers).json()

    response = client.post(f"/brands/{created['id']}/report/export", headers=headers)

    assert response.status_code == 400


@uses_test_session
def test_export_updates_brand_report_pdf_url_and_timestamp(db_session) -> None:
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor4@acme.test")
    headers = _auth_headers(user)
    created = client.post("/brands", json={"name": "Name"}, headers=headers).json()

    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()
    assert brand.report_pdf_url is None

    with patch("httpx.post", return_value=_ok_storage_response()):
        response = client.post(f"/brands/{created['id']}/report/export", headers=headers)

    assert response.status_code == 200
    db_session.refresh(brand)
    assert brand.report_pdf_url == response.json()["url"]
    assert brand.report_pdf_generated_at is not None


@uses_test_session
def test_reexport_after_report_update_produces_new_pdf_not_stale_cache(db_session) -> None:
    """Acceptance criterion: re-exporting after a brand_report update
    must produce an updated PDF at a new URL, rather than reusing/serving
    back the previous export."""
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor5@acme.test")
    headers = _auth_headers(user)
    created = client.post("/brands", json={"name": "Name"}, headers=headers).json()

    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()

    with patch("httpx.post", return_value=_ok_storage_response()) as mock_post:
        first_response = client.post(
            f"/brands/{created['id']}/report/export", headers=headers
        )
        first_content = mock_post.call_args.kwargs["content"]
        first_path = mock_post.call_args.args[0]

        # Update the underlying report content, then re-export.
        brand.brand_report = UPDATED_REPORT
        db_session.flush()

        second_response = client.post(
            f"/brands/{created['id']}/report/export", headers=headers
        )
        second_content = mock_post.call_args.kwargs["content"]
        second_path = mock_post.call_args.args[0]

    assert first_response.status_code == 200
    assert second_response.status_code == 200

    # Different path -> different (non-cached) URL.
    assert first_path != second_path
    assert first_response.json()["url"] != second_response.json()["url"]

    # And the actual bytes stored differ, reflecting the new content.
    assert first_content != second_content
    assert _pdf_text(first_content) != _pdf_text(second_content)
    assert UPDATED_REPORT["voice_and_tone"] in _pdf_text(second_content)
    assert UPDATED_REPORT["voice_and_tone"] not in _pdf_text(first_content)

    db_session.refresh(brand)
    assert brand.report_pdf_url == second_response.json()["url"]


@uses_test_session
def test_reexport_with_unchanged_report_reuses_same_path(db_session) -> None:
    """Idempotency: re-exporting an unchanged report should not create a
    new object at a new path every time — only content changes should."""
    _org, user = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-editor6@acme.test")
    headers = _auth_headers(user)
    created = client.post("/brands", json={"name": "Name"}, headers=headers).json()

    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()

    with patch("httpx.post", return_value=_ok_storage_response()) as mock_post:
        client.post(f"/brands/{created['id']}/report/export", headers=headers)
        first_path = mock_post.call_args.args[0]

        client.post(f"/brands/{created['id']}/report/export", headers=headers)
        second_path = mock_post.call_args.args[0]

    assert first_path == second_path


@uses_test_session
def test_cross_org_cannot_export_report(db_session) -> None:
    _org_a, user_a = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-a@acme.test")
    _org_b, user_b = _create_org_and_user(db_session, UserRole.EDITOR, "pdf-b@acme.test")
    headers_a = _auth_headers(user_a)

    created = client.post("/brands", json={"name": "Org A Brand"}, headers=headers_a).json()
    brand = db_session.get(Brand, created["id"])
    brand.brand_report = REPORT
    db_session.flush()

    response = client.post(
        f"/brands/{created['id']}/report/export", headers=_auth_headers(user_b)
    )
    assert response.status_code == 404
