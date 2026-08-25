import json

from sqlalchemy.orm import Session

from apps.api.models.brand import Brand
from apps.api.models.brand_report_chunk import BrandReportChunk
from packages.integrations.registry import get_embedding_provider


def embed_brand_report(db: Session, brand: Brand) -> list[BrandReportChunk]:
    """Chunks brand.brand_report into one chunk per top-level section and
    embeds each — what get_relevant_brand_context() searches over. Also
    sets Brand.report_embedding (reserved since #4) to a coarse embedding
    of the whole report, for brand-level similarity use cases distinct
    from per-section retrieval.

    Re-embeds rather than appending: this brand's existing chunks are
    deleted before the new ones are inserted, so re-running onboarding
    never leaves stale vectors sitting alongside current ones."""
    if not brand.brand_report:
        return []

    provider = get_embedding_provider()

    db.query(BrandReportChunk).filter(BrandReportChunk.brand_id == brand.id).delete()

    chunks = []
    for section, content in brand.brand_report.items():
        text = content if isinstance(content, str) else json.dumps(content)
        if not text:
            continue
        chunk = BrandReportChunk(
            brand_id=brand.id,
            section=section,
            content=text,
            embedding=provider.embed(text),
        )
        db.add(chunk)
        chunks.append(chunk)

    brand.report_embedding = provider.embed(json.dumps(brand.brand_report, sort_keys=True))

    db.flush()
    for chunk in chunks:
        db.refresh(chunk)
    return chunks
