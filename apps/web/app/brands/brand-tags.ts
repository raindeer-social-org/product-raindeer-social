// Display-only helpers that turn real Brand fields (apps/api/models/brand.py)
// into the tag-chip rows the Brand Data mockup (Raindeer Social.dc.html,
// isBrandData block's `brandCards`) shows for Voice/Audience/Products. None
// of these change the underlying data shape or the brand-form.tsx fields —
// they're purely how brand-card.tsx renders what's already there.

// target_audience is a single free-text string (BrandRead.target_audience),
// not a list — the mockup shows discrete audience-segment chips, so this
// splits on commas/semicolons/newlines as a light heuristic for a nicer
// chip display. A brand whose audience is one plain sentence with no
// separators still renders fine — it's just a single chip.
export function audienceSegments(targetAudience: string | null): string[] {
  if (!targetAudience) return [];
  return targetAudience
    .split(/[,;\n]+/)
    .map((segment) => segment.trim())
    .filter(Boolean);
}

// product_catalog is a genuinely freeform JSONB dict (BrandRead.product_catalog
// is typed `dict | None` server-side with no fixed schema — brand-form.tsx's
// own placeholder, '{ "products": [] }', is just an example, not a contract).
// This extracts a reasonable chip list from the shapes most likely in
// practice, and falls back to the dict's own top-level keys otherwise, so
// *something* real always renders instead of silently showing nothing for
// a brand whose catalog doesn't match the common shape.
export function productNames(catalog: Record<string, unknown> | null): string[] {
  if (!catalog) return [];

  for (const key of ["products", "items", "catalog"]) {
    const value = catalog[key];
    if (!Array.isArray(value)) continue;

    const names = value
      .map((entry): string | null => {
        if (typeof entry === "string") return entry;
        if (entry && typeof entry === "object") {
          const obj = entry as Record<string, unknown>;
          const name = obj.name ?? obj.title ?? obj.label;
          if (typeof name === "string") return name;
        }
        return null;
      })
      .filter((name): name is string => Boolean(name));

    if (names.length > 0) return names;
  }

  return Object.keys(catalog);
}
