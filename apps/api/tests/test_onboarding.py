from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import Brand, Organization, User, UserRole

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


def _setup_brand(db_session, role: UserRole = UserRole.EDITOR, suffix: str = "") -> tuple[Brand, User]:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()

    user = User(
        organization_id=org.id,
        email=f"{role.value}{suffix}@acme.test",
        password_hash=hash_password("test-password"),
        role=role,
    )
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add_all([user, brand])
    db_session.flush()
    return brand, user


def _auth_headers(user: User) -> dict[str, str]:
    token = create_access_token(
        user_id=str(user.id), org_id=str(user.organization_id), role=user.role.value
    )
    return {"Authorization": f"Bearer {token}"}


@uses_test_session
def test_get_onboarding_404_before_anything_saved(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.get(f"/brands/{brand.id}/onboarding", headers=_auth_headers(user))

    assert response.status_code == 404


@uses_test_session
def test_partial_upsert_leaves_incomplete(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful and direct"},
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["voice"] == "Playful and direct"
    assert body["is_complete"] is False


@uses_test_session
def test_upsert_merges_across_calls(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    client.put(f"/brands/{brand.id}/onboarding", json={"voice": "Playful"}, headers=headers)
    response = client.put(
        f"/brands/{brand.id}/onboarding", json={"audience": "Gen Z"}, headers=headers
    )

    body = response.json()
    assert body["voice"] == "Playful"
    assert body["audience"] == "Gen Z"


@uses_test_session
def test_viewer_cannot_upsert_onboarding(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR)
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER)
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful"},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


@uses_test_session
def test_complete_fails_with_missing_fields_listed(db_session) -> None:
    brand, user = _setup_brand(db_session)
    client.put(
        f"/brands/{brand.id}/onboarding",
        json={"voice": "Playful", "audience": "Gen Z"},
        headers=_auth_headers(user),
    )

    response = client.post(f"/brands/{brand.id}/onboarding/complete", headers=_auth_headers(user))

    assert response.status_code == 400
    detail = response.json()["message"]
    assert "product_catalog" in detail
    assert "competitors" in detail
    assert "goals" in detail
    assert "voice" not in detail  # already filled, shouldn't be listed as missing


@uses_test_session
def test_complete_succeeds_once_all_required_fields_present(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    client.put(
        f"/brands/{brand.id}/onboarding",
        json={
            "voice": "Playful and direct",
            "audience": "Gen Z consumers",
            "product_catalog": {"items": ["Widget A", "Widget B"]},
            "competitors": ["Acme Corp", "Widgetron"],
            "goals": ["Increase awareness", "Drive signups"],
        },
        headers=headers,
    )

    response = client.post(f"/brands/{brand.id}/onboarding/complete", headers=headers)

    assert response.status_code == 200
    assert response.json()["is_complete"] is True


@uses_test_session
def test_cannot_edit_after_complete(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    full_payload = {
        "voice": "Playful",
        "audience": "Gen Z",
        "product_catalog": {"items": ["A"]},
        "competitors": ["X"],
        "goals": ["Grow"],
    }
    client.put(f"/brands/{brand.id}/onboarding", json=full_payload, headers=headers)
    client.post(f"/brands/{brand.id}/onboarding/complete", headers=headers)

    response = client.put(
        f"/brands/{brand.id}/onboarding", json={"voice": "Changed"}, headers=headers
    )

    assert response.status_code == 409


@uses_test_session
def test_run_agent_requires_completed_onboarding(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    client.put(f"/brands/{brand.id}/onboarding", json={"voice": "Playful"}, headers=headers)

    response = client.post(f"/brands/{brand.id}/onboarding/run-agent", headers=headers)

    assert response.status_code == 400


@uses_test_session
def test_run_agent_runs_research_then_graph_and_returns_brand_with_report(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)
    full_payload = {
        "voice": "Playful",
        "audience": "Gen Z",
        "product_catalog": {"items": ["A"]},
        "competitors": ["X"],
        "goals": ["Grow"],
    }
    client.put(f"/brands/{brand.id}/onboarding", json=full_payload, headers=headers)
    client.post(f"/brands/{brand.id}/onboarding/complete", headers=headers)

    report = {
        "voice_and_tone": "Playful",
        "audience": "Gen Z",
        "product_catalog_summary": "A",
        "competitive_positioning": "Ahead of X",
    }
    with patch("apps.api.routers.onboarding.run_onboarding_research") as mock_research, patch(
        "apps.api.routers.onboarding.run_onboarding_agent"
    ) as mock_agent, patch("apps.api.routers.onboarding.embed_brand_report") as mock_embed:
        mock_agent.side_effect = lambda db, brand_arg, response_arg, research_arg: (
            setattr(brand_arg, "brand_report", report)
        )
        response = client.post(f"/brands/{brand.id}/onboarding/run-agent", headers=headers)

    assert response.status_code == 200
    assert response.json()["brand_report"] == report
    mock_research.assert_called_once()
    mock_agent.assert_called_once()
    mock_embed.assert_called_once()


@uses_test_session
def test_viewer_cannot_run_agent(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER, suffix="-2")
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.post(
        f"/brands/{brand.id}/onboarding/run-agent", headers=_auth_headers(viewer)
    )

    assert response.status_code == 403


@uses_test_session
def test_research_stream_emits_log_and_done_events(db_session) -> None:
    brand, user = _setup_brand(db_session)
    headers = _auth_headers(user)

    from packages.integrations.search.base import SearchResult

    fake_results = [SearchResult(title="Acme Widgets", url="https://acme.test", content="...")]
    with patch(
        "apps.api.routers.onboarding.search_brand_overview", return_value=fake_results
    ) as mock_search:
        response = client.get(f"/brands/{brand.id}/onboarding/research-stream", headers=headers)

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    mock_search.assert_called_once_with(brand.name)
    body = response.text
    assert "event: log" in body
    assert "event: signal" in body
    assert "Acme Widgets" in body
    assert "event: done" in body
    assert '"count": 1' in body


@uses_test_session
def test_research_stream_requires_org_membership(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")

    response = client.get(
        f"/brands/{brand.id}/onboarding/research-stream", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


@uses_test_session
def test_cross_org_onboarding_access_returns_404(db_session) -> None:
    brand, _owner = _setup_brand(db_session, UserRole.EDITOR, suffix="-1")
    _brand2, other_user = _setup_brand(db_session, UserRole.EDITOR, suffix="-2")

    response = client.get(
        f"/brands/{brand.id}/onboarding", headers=_auth_headers(other_user)
    )

    assert response.status_code == 404


# --- Deeper questionnaire fields (Issue #144) ---


@uses_test_session
def test_upsert_accepts_deeper_questionnaire_fields(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.put(
        f"/brands/{brand.id}/onboarding",
        json={
            "mission": "Make widgets everyone actually wants.",
            "content_dos_donts": ["Never mention competitor X by name"],
            "posting_cadence": "A few times a week",
        },
        headers=_auth_headers(user),
    )

    assert response.status_code == 200
    body = response.json()
    assert body["mission"] == "Make widgets everyone actually wants."
    assert body["content_dos_donts"] == ["Never mention competitor X by name"]
    assert body["posting_cadence"] == "A few times a week"


# --- Real voice recording + transcription (Issue #144) ---

_SPEECH_PATCH_TARGET = "apps.api.routers.onboarding.get_speech_provider"
_STORAGE_PATCH_TARGET = "apps.api.routers.onboarding.get_storage_provider"


class _FakeTranscription:
    def __init__(self, text: str) -> None:
        self.text = text
        self.language = "en"
        self.duration_seconds = 3.5


@uses_test_session
def test_voice_answer_transcribes_and_stores_audio(db_session) -> None:
    brand, user = _setup_brand(db_session)

    fake_speech = MagicMock()
    fake_speech.transcribe.return_value = _FakeTranscription("We sell widgets to small businesses.")
    fake_storage = MagicMock()
    fake_storage.upload.return_value = "https://storage.test/onboarding/voice/audience/take.webm"

    with patch(_SPEECH_PATCH_TARGET, return_value=fake_speech), patch(
        _STORAGE_PATCH_TARGET, return_value=fake_storage
    ):
        response = client.post(
            f"/brands/{brand.id}/onboarding/voice-answers",
            data={"question_id": "audience"},
            files={"file": ("answer.webm", b"fake-audio-bytes", "audio/webm")},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["transcript"] == "We sell widgets to small businesses."
    assert body["audio_url"] == "https://storage.test/onboarding/voice/audience/take.webm"
    assert body["question_id"] == "audience"
    fake_speech.transcribe.assert_called_once()
    fake_storage.upload.assert_called_once()

    listed = client.get(f"/brands/{brand.id}/onboarding/voice-answers", headers=_auth_headers(user))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@uses_test_session
def test_voice_answer_requires_write_role(db_session) -> None:
    brand, viewer = _setup_brand(db_session, UserRole.VIEWER)

    response = client.post(
        f"/brands/{brand.id}/onboarding/voice-answers",
        data={"question_id": "audience"},
        files={"file": ("answer.webm", b"data", "audio/webm")},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403


# --- Real asset uploads (Issue #144) ---


@uses_test_session
def test_upload_onboarding_asset_stores_and_lists(db_session) -> None:
    brand, user = _setup_brand(db_session)

    fake_storage = MagicMock()
    fake_storage.upload.return_value = "https://storage.test/onboarding/assets/product_photos/x.png"

    with patch(_STORAGE_PATCH_TARGET, return_value=fake_storage):
        response = client.post(
            f"/brands/{brand.id}/onboarding/assets",
            data={"slot": "product_photos"},
            files={"file": ("photo.png", b"fake-bytes", "image/png")},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["slot"] == "product_photos"
    assert body["url"] == "https://storage.test/onboarding/assets/product_photos/x.png"
    assert body["filename"] == "photo.png"

    listed = client.get(f"/brands/{brand.id}/onboarding/assets", headers=_auth_headers(user))
    assert listed.status_code == 200
    assert len(listed.json()) == 1


@uses_test_session
def test_reuploading_to_same_slot_replaces_it(db_session) -> None:
    brand, user = _setup_brand(db_session)
    fake_storage = MagicMock()

    with patch(_STORAGE_PATCH_TARGET, return_value=fake_storage):
        fake_storage.upload.return_value = "https://storage.test/first.png"
        client.post(
            f"/brands/{brand.id}/onboarding/assets",
            data={"slot": "style_guide"},
            files={"file": ("first.png", b"data-1", "image/png")},
            headers=_auth_headers(user),
        )

        fake_storage.upload.return_value = "https://storage.test/second.png"
        response = client.post(
            f"/brands/{brand.id}/onboarding/assets",
            data={"slot": "style_guide"},
            files={"file": ("second.png", b"data-2", "image/png")},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json()["url"] == "https://storage.test/second.png"

    listed = client.get(f"/brands/{brand.id}/onboarding/assets", headers=_auth_headers(user))
    assert len(listed.json()) == 1


@uses_test_session
def test_upload_onboarding_asset_rejects_unknown_slot(db_session) -> None:
    brand, user = _setup_brand(db_session)

    response = client.post(
        f"/brands/{brand.id}/onboarding/assets",
        data={"slot": "not_a_real_slot"},
        files={"file": ("photo.png", b"data", "image/png")},
        headers=_auth_headers(user),
    )

    assert response.status_code == 400
