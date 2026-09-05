import type { Brand } from "@/lib/api";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { audienceSegments, productNames } from "./brand-tags";

function TagRow({ label, meta, tags }: { label: string; meta?: string; tags: string[] }) {
  if (tags.length === 0) return null;
  return (
    <div className="mt-3">
      <div className="mb-1.5 flex items-center gap-2">
        <span className="text-[11px] font-bold uppercase tracking-wide text-ink-300">{label}</span>
        {meta ? (
          <span className="rounded-full bg-canvas px-2 py-0.5 text-[10.5px] font-semibold text-ink-300">
            {meta}
          </span>
        ) : null}
      </div>
      <div className="flex flex-wrap gap-1.5">
        {tags.map((tag, index) => (
          <Badge key={`${tag}-${index}`} tone="slate">
            {tag}
          </Badge>
        ))}
      </div>
    </div>
  );
}

export function BrandCard({
  brand,
  onEdit,
  onDelete,
  onExportPdf,
  onReinterview,
  isExporting,
}: {
  brand: Brand;
  onEdit: () => void;
  onDelete: () => void;
  onExportPdf: () => void;
  onReinterview: () => void;
  isExporting?: boolean;
}) {
  const voice = brand.tone_descriptors ?? [];
  const audience = audienceSegments(brand.target_audience);
  const products = productNames(brand.product_catalog);

  return (
    <Card role="article" aria-label={brand.name} className="flex h-full flex-col p-5">
      <div className="flex items-center gap-3">
        <Avatar name={brand.name} src={brand.logo_url} size="lg" />
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-ink-950">{brand.name}</h3>
          {brand.industry ? (
            <Badge tone="brand" className="mt-1">
              {brand.industry}
            </Badge>
          ) : null}
        </div>
      </div>

      {brand.colors && brand.colors.length > 0 ? (
        <div className="mt-3">
          <span className="text-[11px] font-bold uppercase tracking-wide text-ink-300">Palette</span>
          <div className="mt-1.5 flex flex-wrap items-center gap-1.5">
            {brand.colors.map((color, index) => (
              <span
                key={`${color}-${index}`}
                title={color}
                className="h-6 w-6 rounded-full border border-line"
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        </div>
      ) : null}

      <TagRow label="Voice" tags={voice} />
      <TagRow label="Audience" tags={audience} />
      <TagRow label="Products" tags={products} />

      {/* Compliance rules aren't a distinct Brand field yet (see
          apps/api/models/brand.py) — nothing real backs this section today,
          so it says so instead of fabricating chips. */}
      <div className="mt-3">
        <span className="text-[11px] font-bold uppercase tracking-wide text-ink-300">Compliance rules</span>
        <p className="mt-1.5 text-xs text-ink-300">
          Not tracked as a distinct field yet — Neer&apos;s guardrails come from the tone descriptors and
          brand report above for now.
        </p>
      </div>

      <div className="mt-4 flex flex-wrap items-center justify-end gap-2 border-t border-line-faint pt-3">
        <Button variant="outline" size="sm" isLoading={isExporting} onClick={onExportPdf}>
          Export brand PDF
        </Button>
        <Button variant="outline" size="sm" onClick={onReinterview}>
          Re-interview with Aarav
        </Button>
        <Button variant="outline" size="sm" onClick={onEdit}>
          Edit
        </Button>
        <Button variant="danger" size="sm" onClick={onDelete}>
          Delete
        </Button>
      </div>
    </Card>
  );
}
