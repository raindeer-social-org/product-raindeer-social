import type { Brand } from "@/lib/api";
import { Avatar } from "@/components/ui/Avatar";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";

export function BrandCard({
  brand,
  onEdit,
  onDelete,
}: {
  brand: Brand;
  onEdit: () => void;
  onDelete: () => void;
}) {
  return (
    <Card role="article" aria-label={brand.name} className="flex h-full flex-col p-5">
      <div className="flex items-center gap-3">
        <Avatar name={brand.name} src={brand.logo_url} size="lg" />
        <div className="min-w-0">
          <h3 className="truncate text-sm font-semibold text-slate-900">{brand.name}</h3>
          {brand.industry ? (
            <Badge tone="brand" className="mt-1">
              {brand.industry}
            </Badge>
          ) : null}
        </div>
      </div>

      {brand.target_audience ? (
        <p className="mt-3 line-clamp-2 text-sm text-slate-500">{brand.target_audience}</p>
      ) : null}

      {brand.colors && brand.colors.length > 0 ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5">
          {brand.colors.map((color, index) => (
            <span
              key={`${color}-${index}`}
              title={color}
              className="h-5 w-5 rounded-full border border-slate-200"
              style={{ backgroundColor: color }}
            />
          ))}
        </div>
      ) : null}

      {brand.tone_descriptors && brand.tone_descriptors.length > 0 ? (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {brand.tone_descriptors.map((tone) => (
            <Badge key={tone} tone="slate">
              {tone}
            </Badge>
          ))}
        </div>
      ) : null}

      <div className="mt-4 flex justify-end gap-2 border-t border-slate-100 pt-3">
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
