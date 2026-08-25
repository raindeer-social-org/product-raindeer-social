import hashlib
from unittest.mock import patch

from apps.api.models import Brand, BrandReportChunk, Organization
from apps.api.services.brand_retrieval import get_relevant_brand_context
from packages.agents.onboarding.embedding import embed_brand_report

REPORT = {
    "voice_and_tone": "Playful and direct.",
    "audience": "Gen Z consumers who value sustainability.",
    "product_catalog_summary": "A line of eco-friendly widgets.",
    "competitive_positioning": "Positioned as the premium, sustainable alternative to Widgetron.",
}


def _setup_brand(db_session) -> Brand:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets", brand_report=REPORT)
    db_session.add(brand)
    db_session.flush()
    return brand


def _fake_embed(text: str) -> list[float]:
    # Deterministic one-hot-ish "embedding" (index picked by hashing the
    # text) so cosine-distance ordering in tests is predictable without a
    # real embeddings API call — identical text always lands on the same
    # dimension (distance 0), different text lands on a different one
    # (near-orthogonal, distance ~1), unlike a uniform vector where every
    # direction is parallel regardless of magnitude.
    vec = [0.0] * 1536
    idx = int(hashlib.sha256(text.encode()).hexdigest(), 16) % 1536
    vec[idx] = 1.0
    return vec


def test_embed_brand_report_creates_one_chunk_per_section(db_session) -> None:
    brand = _setup_brand(db_session)

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.side_effect = _fake_embed
        chunks = embed_brand_report(db_session, brand)

    assert len(chunks) == 4
    sections = {c.section for c in chunks}
    assert sections == set(REPORT.keys())
    assert all(len(c.embedding) == 1536 for c in chunks)


def test_embed_brand_report_sets_coarse_report_embedding(db_session) -> None:
    brand = _setup_brand(db_session)

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.side_effect = _fake_embed
        embed_brand_report(db_session, brand)

    db_session.refresh(brand)
    assert brand.report_embedding is not None
    assert len(brand.report_embedding) == 1536


def test_embed_brand_report_reembeds_without_appending_stale_chunks(db_session) -> None:
    brand = _setup_brand(db_session)

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.side_effect = _fake_embed
        embed_brand_report(db_session, brand)
        embed_brand_report(db_session, brand)

    rows = db_session.query(BrandReportChunk).filter(BrandReportChunk.brand_id == brand.id).all()
    assert len(rows) == 4  # not 8 — old chunks were replaced, not appended to


def test_embed_brand_report_noop_when_no_report(db_session) -> None:
    org = Organization(name="Acme Agency")
    db_session.add(org)
    db_session.flush()
    brand = Brand(organization_id=org.id, name="Acme Widgets")
    db_session.add(brand)
    db_session.flush()

    chunks = embed_brand_report(db_session, brand)

    assert chunks == []


def test_get_relevant_brand_context_returns_top_k_closest_chunks(db_session) -> None:
    brand = _setup_brand(db_session)

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.side_effect = _fake_embed
        embed_brand_report(db_session, brand)

    # Query embedding identical to the "audience" chunk's embedding (same
    # text length trick) — it should come back first.
    target_text = REPORT["audience"]
    with patch("apps.api.services.brand_retrieval.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.return_value = _fake_embed(target_text)
        results = get_relevant_brand_context(db_session, brand.id, query="anything", top_k=2)

    assert len(results) == 2
    assert results[0]["section"] == "audience"


def test_get_relevant_brand_context_scoped_to_brand(db_session) -> None:
    brand = _setup_brand(db_session)
    other_org = Organization(name="Other Org")
    db_session.add(other_org)
    db_session.flush()
    other_brand = Brand(organization_id=other_org.id, name="Other Brand", brand_report=REPORT)
    db_session.add(other_brand)
    db_session.flush()

    with patch("packages.agents.onboarding.embedding.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.side_effect = _fake_embed
        embed_brand_report(db_session, brand)
        embed_brand_report(db_session, other_brand)

    with patch("apps.api.services.brand_retrieval.get_embedding_provider") as mock_provider:
        mock_provider.return_value.embed.return_value = _fake_embed("query")
        results = get_relevant_brand_context(db_session, brand.id, query="query", top_k=10)

    assert len(results) == 4  # only this brand's chunks, not other_brand's
