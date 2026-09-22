from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from apps.api.auth.jwt import create_access_token, hash_password
from apps.api.main import app
from apps.api.models import (
    MAX_DYNAMIC_PAGES,
    Brand,
    OnboardingDynamicAnswer,
    Organization,
    User,
    UserRole,
)

client = TestClient(app)
uses_test_session = pytest.mark.usefixtures("override_get_db")


def _session_local_stub(db_session):
    """research-stream's website-scrape branch (issue #152) intentionally
    opens its own SessionLocal() rather than reusing Depends(get_db) — see
    that function's docstring for why (a DetachedInstanceError fix: the
    request-scoped session is already closed by the time this lazily-
    streamed branch runs). override_get_db's db_session fixture only
    patches Depends(get_db), so a real SessionLocal() call here would open
    a second, separate connection that can't see this test's uncommitted
    setup data. This stub makes `apps.api.routers.onboarding.SessionLocal`
    return a thin proxy onto the same db_session instead — delegating
    reads/writes to it while no-op'ing commit/close so the test's own
    transaction (rolled back in the db_session fixture's teardown) stays
    in charge of the connection throughout."""

    class _Proxy:
        def get(self, *args, **kwargs):
            return db_session.get(*args, **kwargs)

        def add(self, *args, **kwargs):
            db_session.add(*args, **kwargs)

        def flush(self, *args, **kwargs):
            db_session.flush(*args, **kwargs)

        def refresh(self, *args, **kwargs):
            db_session.refresh(*args, **kwargs)

        def commit(self):
            db_session.flush()

        def rollback(self):
            pass

        def close(self):
            pass

    return lambda: _Proxy()


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
def test_complete_succeeds_with_no_fields_filled(db_session) -> None:
    """OnboardingResponse's fixed fields are optional enrichment now, not a
    completion gate — a brand can finish onboarding having answered none of
    them directly, with Aarav's dynamic phase (OnboardingDynamicAnswer)
    covering the same ground instead. See OnboardingResponse's docstring."""
    brand, user = _setup_brand(db_session)

    response = client.post(f"/brands/{brand.id}/onboarding/complete", headers=_auth_headers(user))

    assert response.status_code == 200
    assert response.json()["is_complete"] is True


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
        mock_agent.side_effect = lambda db, brand_arg, response_arg, research_arg, dynamic_qa=None: (
            setattr(brand_arg, "brand_report", report)
        )
        response = client.post(f"/brands/{brand.id}/onboarding/run-agent", headers=headers)

    assert response.status_code == 200
    assert response.json()["brand_report"] == report
    mock_research.assert_called_once()
    mock_agent.assert_called_once()
    mock_embed.assert_called_once()


@uses_test_session
def test_run_agent_passes_dynamic_qa_history_to_synthesis(db_session) -> None:
    """Issue #158 — Aarav's adaptive follow-up Q&A (Issue #153) must reach
    onboarding synthesis, not just the fixed questionnaire."""
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

    db_session.add(
        OnboardingDynamicAnswer(
            brand_id=brand.id,
            page_index=1,
            question={"id": "integrations", "title": "What tools does Acme integrate with?"},
            answer="QuickBooks and Stripe",
        )
    )
    db_session.flush()

    with patch("apps.api.routers.onboarding.run_onboarding_research"), patch(
        "apps.api.routers.onboarding.run_onboarding_agent"
    ) as mock_agent, patch("apps.api.routers.onboarding.embed_brand_report"):
        response = client.post(f"/brands/{brand.id}/onboarding/run-agent", headers=headers)

    assert response.status_code == 200
    _args, kwargs = mock_agent.call_args
    assert kwargs["dynamic_qa"] == [
        {
            "page_index": 1,
            "answers": [
                {
                    "question": {"id": "integrations", "title": "What tools does Acme integrate with?"},
                    "answer": "QuickBooks and Stripe",
                }
            ],
        }
    ]


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
def test_research_stream_emits_extracted_event_when_brand_has_a_website(db_session) -> None:
    """Issue #152 — the real scrape phase only runs (and only emits
    "extracted") when the brand has a website on file; the search-only
    preview above (test_research_stream_emits_log_and_done_events, no
    website set) must keep working unchanged."""
    brand, user = _setup_brand(db_session)
    brand.product_catalog = {"website": "https://acme.test"}
    db_session.flush()
    headers = _auth_headers(user)

    from apps.api.models import OnboardingResearch
    from packages.integrations.search.base import SearchResult

    def fake_run_website_scrape(db, brand_arg, url):
        assert url == "https://acme.test"
        research = OnboardingResearch(
            brand_id=brand_arg.id,
            website_summary="Acme Widgets makes durable widgets.",
            website_logo_url="https://storage.test/scraped-logo.png",
            website_colors=["#1b4dff"],
            website_social_links={"instagram": "https://instagram.com/acme"},
        )
        db.add(research)
        db.flush()
        return research

    with (
        patch("apps.api.routers.onboarding.search_brand_overview", return_value=[SearchResult(title="x", url="https://acme.test", content="...")]),
        patch("apps.api.routers.onboarding.run_website_scrape", side_effect=fake_run_website_scrape) as mock_scrape,
        patch("apps.api.routers.onboarding.SessionLocal", new=_session_local_stub(db_session)),
    ):
        response = client.get(f"/brands/{brand.id}/onboarding/research-stream", headers=headers)

    assert response.status_code == 200
    mock_scrape.assert_called_once()
    body = response.text
    assert "event: extracted" in body
    assert "scraped-logo.png" in body
    assert '"colors": ["#1b4dff"]' in body
    assert "instagram.com/acme" in body
    assert "event: done" in body


@uses_test_session
def test_research_stream_skips_extraction_event_when_scrape_finds_nothing(db_session) -> None:
    brand, user = _setup_brand(db_session)
    brand.product_catalog = {"website": "https://acme.test"}
    db_session.flush()
    headers = _auth_headers(user)

    from apps.api.models import OnboardingResearch

    def fake_run_website_scrape(db, brand_arg, url):
        research = OnboardingResearch(brand_id=brand_arg.id)
        db.add(research)
        db.flush()
        return research

    with (
        patch("apps.api.routers.onboarding.search_brand_overview", return_value=[]),
        patch("apps.api.routers.onboarding.run_website_scrape", side_effect=fake_run_website_scrape),
        patch("apps.api.routers.onboarding.SessionLocal", new=_session_local_stub(db_session)),
    ):
        response = client.get(f"/brands/{brand.id}/onboarding/research-stream", headers=headers)

    assert response.status_code == 200
    assert "event: extracted" not in response.text
    assert "event: done" in response.text


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
def test_voice_answer_survives_storage_outage(db_session) -> None:
    """A StorageProvider failure re-hosting the raw audio must not cost the
    brand a transcript that already succeeded — regression test for a real
    bug where this endpoint raised straight through a successful
    transcription and lost it."""
    brand, user = _setup_brand(db_session)

    fake_speech = MagicMock()
    fake_speech.transcribe.return_value = _FakeTranscription("We sell widgets to small businesses.")
    fake_storage = MagicMock()
    fake_storage.upload.side_effect = ConnectionError("storage unreachable")

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
    assert body["audio_url"] is None


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


# --- Adaptive, LLM-generated follow-up questions (Issue #153) ---

_NEXT_QUESTIONS_PATCH_TARGET = "apps.api.routers.onboarding.generate_next_page"
_DYNAMIC_LLM_PATCH_TARGET = "packages.agents.onboarding.dynamic_questions.get_llm_provider"


@uses_test_session
def test_next_questions_first_call_generates_page_one(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(_NEXT_QUESTIONS_PATCH_TARGET) as mock_generate:
        mock_generate.return_value = (
            False,
            [{"id": "integrations", "type": "text", "title": "What do you integrate with?", "sub": "", "options": None}],
        )
        response = client.post(
            f"/brands/{brand.id}/onboarding/next-questions",
            json={},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    body = response.json()
    assert body["done"] is False
    assert body["page_index"] == 1
    assert body["questions"][0]["id"] == "integrations"
    # First call (page_index defaults to 0, no answers) generates page 1 —
    # confirm the router asked for page 1, not page 0.
    assert mock_generate.call_args.args[3] == 1


@uses_test_session
def test_next_questions_persists_submitted_answers(db_session) -> None:
    brand, user = _setup_brand(db_session)
    question = {"id": "integrations", "type": "text", "title": "What do you integrate with?", "sub": "", "options": None}

    with patch(_NEXT_QUESTIONS_PATCH_TARGET) as mock_generate:
        mock_generate.return_value = (True, [])
        response = client.post(
            f"/brands/{brand.id}/onboarding/next-questions",
            json={"page_index": 1, "answers": [{"question": question, "answer": "QuickBooks and Stripe"}]},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json() == {"done": True, "page_index": 0, "questions": []}

    stored = db_session.query(OnboardingDynamicAnswer).filter_by(brand_id=brand.id).all()
    assert len(stored) == 1
    assert stored[0].page_index == 1
    assert stored[0].question["id"] == "integrations"
    assert stored[0].answer == "QuickBooks and Stripe"

    # The next generation call should see what was just persisted.
    prior_pages_arg = mock_generate.call_args.args[2]
    assert prior_pages_arg == [{"page_index": 1, "answers": [{"question": question, "answer": "QuickBooks and Stripe"}]}]


@uses_test_session
def test_next_questions_hard_caps_without_calling_llm(db_session) -> None:
    """page_index=MAX_DYNAMIC_PAGES means the next page would be past the
    cap — generate_next_page must short-circuit before ever reaching the
    LLM provider."""
    brand, user = _setup_brand(db_session)

    with patch(_DYNAMIC_LLM_PATCH_TARGET) as mock_get_llm:
        response = client.post(
            f"/brands/{brand.id}/onboarding/next-questions",
            json={"page_index": MAX_DYNAMIC_PAGES, "answers": []},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json() == {"done": True, "page_index": 0, "questions": []}
    mock_get_llm.assert_not_called()


@uses_test_session
def test_next_questions_degrades_gracefully_on_llm_failure(db_session) -> None:
    brand, user = _setup_brand(db_session)

    with patch(_DYNAMIC_LLM_PATCH_TARGET) as mock_get_llm:
        mock_get_llm.return_value.complete.side_effect = RuntimeError("provider down")
        response = client.post(
            f"/brands/{brand.id}/onboarding/next-questions",
            json={},
            headers=_auth_headers(user),
        )

    assert response.status_code == 200
    assert response.json() == {"done": True, "page_index": 0, "questions": []}


@uses_test_session
def test_viewer_cannot_call_next_questions(db_session) -> None:
    brand, editor = _setup_brand(db_session, UserRole.EDITOR)
    _brand2, viewer = _setup_brand(db_session, UserRole.VIEWER)
    viewer.organization_id = editor.organization_id
    db_session.flush()

    response = client.post(
        f"/brands/{brand.id}/onboarding/next-questions",
        json={},
        headers=_auth_headers(viewer),
    )

    assert response.status_code == 403
