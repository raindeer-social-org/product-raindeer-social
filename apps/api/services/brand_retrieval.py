import uuid

from sqlalchemy.orm import Session

from apps.api.models.brand_report_chunk import BrandReportChunk
from packages.integrations.registry import get_embedding_provider


def get_relevant_brand_context(
    db: Session, brand_id: uuid.UUID, query: str, top_k: int = 3
) -> list[dict]:
    """Returns the top_k brand_report_chunks most relevant to `query`, via
    pgvector cosine-distance similarity search. What M3 agents (Research/
    Creative/Generation/Reviewer) call instead of reading brand_report's
    raw JSONB and stuffing the whole thing into every prompt."""
    provider = get_embedding_provider()
    query_embedding = provider.embed(query)

    rows = (
        db.query(BrandReportChunk)
        .filter(BrandReportChunk.brand_id == brand_id)
        .order_by(BrandReportChunk.embedding.cosine_distance(query_embedding))
        .limit(top_k)
        .all()
    )
    return [{"section": row.section, "content": row.content} for row in rows]
