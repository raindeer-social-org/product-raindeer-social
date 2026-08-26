"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { Button } from "@/components/ui/Button";
import { Field, Input, Textarea } from "@/components/ui/Input";
import type { OnboardingResponseData, OnboardingUpsertInput } from "@/lib/api";

function toCommaList(value: string): string[] {
  return value
    .split(",")
    .map((item) => item.trim())
    .filter(Boolean);
}

function fromList(value: string[] | null | undefined): string {
  return (value ?? []).join(", ");
}

export function OnboardingForm({
  initialValues,
  isSubmitting,
  onSubmit,
}: {
  initialValues: OnboardingResponseData | null;
  isSubmitting: boolean;
  onSubmit: (payload: OnboardingUpsertInput) => void | Promise<void>;
}) {
  const [voice, setVoice] = useState(initialValues?.voice ?? "");
  const [audience, setAudience] = useState(initialValues?.audience ?? "");
  const [productCatalogText, setProductCatalogText] = useState(
    initialValues?.product_catalog ? JSON.stringify(initialValues.product_catalog, null, 2) : ""
  );
  const [competitors, setCompetitors] = useState(fromList(initialValues?.competitors));
  const [goals, setGoals] = useState(fromList(initialValues?.goals));
  const [jsonError, setJsonError] = useState<string | null>(null);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setJsonError(null);

    let productCatalog: Record<string, unknown> | null = null;
    if (productCatalogText.trim()) {
      try {
        productCatalog = JSON.parse(productCatalogText);
      } catch {
        setJsonError("Product catalog must be valid JSON.");
        return;
      }
    }

    await onSubmit({
      voice: voice.trim() || null,
      audience: audience.trim() || null,
      product_catalog: productCatalog,
      competitors: toCommaList(competitors),
      goals: toCommaList(goals),
    });
  }

  return (
    <form onSubmit={handleSubmit} noValidate className="space-y-4">
      <Field
        label="Brand voice"
        htmlFor="onboarding-voice"
        hint="Describe how your brand sounds — tone, personality, style."
      >
        <Textarea id="onboarding-voice" value={voice} onChange={(event) => setVoice(event.target.value)} />
      </Field>

      <Field label="Audience" htmlFor="onboarding-audience" hint="Who are you trying to reach?">
        <Textarea
          id="onboarding-audience"
          value={audience}
          onChange={(event) => setAudience(event.target.value)}
        />
      </Field>

      <Field
        label="Product catalog"
        htmlFor="onboarding-product-catalog"
        hint="Paste JSON describing your products or services."
        error={jsonError}
      >
        <Textarea
          id="onboarding-product-catalog"
          value={productCatalogText}
          onChange={(event) => setProductCatalogText(event.target.value)}
          className="min-h-[8rem] font-mono text-xs"
          placeholder='{"products": [{"name": "Widget Pro", "price": "$49"}]}'
        />
      </Field>

      <Field label="Competitors" htmlFor="onboarding-competitors" hint="Comma-separated list.">
        <Input
          id="onboarding-competitors"
          value={competitors}
          onChange={(event) => setCompetitors(event.target.value)}
          placeholder="Acme Co, Widget Inc"
        />
      </Field>

      <Field label="Goals" htmlFor="onboarding-goals" hint="Comma-separated list.">
        <Input
          id="onboarding-goals"
          value={goals}
          onChange={(event) => setGoals(event.target.value)}
          placeholder="Grow LinkedIn following, launch product X"
        />
      </Field>

      <Button type="submit" isLoading={isSubmitting} disabled={isSubmitting}>
        {isSubmitting ? "Saving…" : "Save answers"}
      </Button>
    </form>
  );
}
