"use client";

import { useRef, useState } from "react";
import type { ChangeEvent, FormEvent } from "react";
import type { Brand, BrandInput, BrandUpdateInput } from "@/lib/api";
import { Button } from "@/components/ui/Button";
import { Field, Input, Textarea } from "@/components/ui/Input";

interface BrandFormProps {
  /** null when creating a new brand, the existing brand when editing one. */
  brand: Brand | null;
  onCancel: () => void;
  onSubmit: (payload: BrandInput | BrandUpdateInput) => Promise<void>;
  /** Only available when editing — a brand must exist before it can have a logo. */
  onUploadLogo?: (file: File) => Promise<void>;
  onRemoveLogo?: () => Promise<void>;
}

function joinList(values: string[] | null | undefined): string {
  return values?.join(", ") ?? "";
}

// Comma-separated free text -> a trimmed, non-empty string array, or null
// when the field was left blank (so PATCH payloads can clear a field by
// submitting an empty input rather than omitting it).
function parseList(value: string): string[] | null {
  const items = value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : null;
}

export function BrandForm({ brand, onCancel, onSubmit, onUploadLogo, onRemoveLogo }: BrandFormProps) {
  const isEdit = brand !== null;

  const [name, setName] = useState(brand?.name ?? "");
  const [industry, setIndustry] = useState(brand?.industry ?? "");
  const [targetAudience, setTargetAudience] = useState(brand?.target_audience ?? "");
  const [colors, setColors] = useState(joinList(brand?.colors));
  const [toneDescriptors, setToneDescriptors] = useState(joinList(brand?.tone_descriptors));
  const [productCatalog, setProductCatalog] = useState(
    brand?.product_catalog ? JSON.stringify(brand.product_catalog, null, 2) : ""
  );
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isUploadingLogo, setIsUploadingLogo] = useState(false);
  const [isRemovingLogo, setIsRemovingLogo] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const colorSwatches = parseList(colors) ?? [];

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();

    if (!name.trim()) {
      setError("Name is required.");
      return;
    }

    let parsedCatalog: Record<string, unknown> | null = null;
    if (productCatalog.trim()) {
      try {
        parsedCatalog = JSON.parse(productCatalog);
      } catch {
        setError("Product catalog must be valid JSON.");
        return;
      }
    }

    setError(null);
    setIsSubmitting(true);
    try {
      await onSubmit({
        name: name.trim(),
        industry: industry.trim() || null,
        target_audience: targetAudience.trim() || null,
        colors: parseList(colors),
        tone_descriptors: parseList(toneDescriptors),
        product_catalog: parsedCatalog,
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to save brand.");
      setIsSubmitting(false);
    }
  }

  async function handleLogoFileChange(event: ChangeEvent<HTMLInputElement>) {
    const file = event.target.files?.[0];
    event.target.value = "";
    if (!file || !onUploadLogo) return;

    setIsUploadingLogo(true);
    try {
      await onUploadLogo(file);
    } finally {
      setIsUploadingLogo(false);
    }
  }

  async function handleRemoveLogoClick() {
    if (!onRemoveLogo) return;
    setIsRemovingLogo(true);
    try {
      await onRemoveLogo();
    } finally {
      setIsRemovingLogo(false);
    }
  }

  return (
    <form id="brand-form" onSubmit={handleSubmit} noValidate className="space-y-4">
      {isEdit && brand ? (
        <div className="space-y-1.5">
          <span className="block text-sm font-medium text-slate-700">Logo</span>
          <div className="flex items-center gap-3">
            {brand.logo_url ? (
              // eslint-disable-next-line @next/next/no-img-element
              <img
                src={brand.logo_url}
                alt={`${brand.name} logo`}
                className="h-12 w-12 rounded-full object-cover"
              />
            ) : (
              <div className="flex h-12 w-12 items-center justify-center rounded-full bg-slate-100 text-xs font-medium text-slate-400">
                No logo
              </div>
            )}
            <input
              ref={fileInputRef}
              type="file"
              accept="image/*"
              aria-label="Upload logo"
              className="hidden"
              onChange={handleLogoFileChange}
            />
            <Button
              type="button"
              variant="outline"
              size="sm"
              isLoading={isUploadingLogo}
              onClick={() => fileInputRef.current?.click()}
            >
              {brand.logo_url ? "Replace logo" : "Upload logo"}
            </Button>
            {brand.logo_url ? (
              <Button
                type="button"
                variant="outline"
                size="sm"
                isLoading={isRemovingLogo}
                disabled={isUploadingLogo}
                onClick={handleRemoveLogoClick}
              >
                Remove logo
              </Button>
            ) : null}
          </div>
        </div>
      ) : null}

      <Field label="Name" htmlFor="brand-name" required>
        <Input id="brand-name" value={name} onChange={(e) => setName(e.target.value)} required />
      </Field>

      <Field label="Industry" htmlFor="brand-industry">
        <Input id="brand-industry" value={industry ?? ""} onChange={(e) => setIndustry(e.target.value)} />
      </Field>

      <Field label="Target audience" htmlFor="brand-target-audience">
        <Textarea
          id="brand-target-audience"
          rows={2}
          value={targetAudience ?? ""}
          onChange={(e) => setTargetAudience(e.target.value)}
        />
      </Field>

      <Field
        label="Brand colors"
        htmlFor="brand-colors"
        hint="Comma-separated hex colors, e.g. #FF5733, #1A1A2E"
      >
        <Input id="brand-colors" value={colors} onChange={(e) => setColors(e.target.value)} />
        {colorSwatches.length > 0 ? (
          <div className="mt-2 flex flex-wrap items-center gap-1.5">
            {colorSwatches.map((color, index) => (
              <span
                key={`${color}-${index}`}
                title={color}
                className="h-5 w-5 rounded-full border border-slate-200"
                style={{ backgroundColor: color }}
              />
            ))}
          </div>
        ) : null}
      </Field>

      <Field
        label="Tone descriptors"
        htmlFor="brand-tone-descriptors"
        hint="Comma-separated, e.g. playful, confident, concise"
      >
        <Input
          id="brand-tone-descriptors"
          value={toneDescriptors}
          onChange={(e) => setToneDescriptors(e.target.value)}
        />
      </Field>

      <Field
        label="Product catalog"
        htmlFor="brand-product-catalog"
        hint="Raw JSON — leave blank for none."
      >
        <Textarea
          id="brand-product-catalog"
          rows={5}
          className="font-mono text-xs"
          value={productCatalog}
          onChange={(e) => setProductCatalog(e.target.value)}
          placeholder={'{\n  "products": []\n}'}
        />
      </Field>

      {error ? (
        <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
          {error}
        </p>
      ) : null}

      <div className="flex justify-end gap-2 pt-2">
        <Button type="button" variant="outline" onClick={onCancel} disabled={isSubmitting}>
          Cancel
        </Button>
        <Button type="submit" isLoading={isSubmitting}>
          {isEdit ? "Save changes" : "Create brand"}
        </Button>
      </div>
    </form>
  );
}
