"use client";

import { useState } from "react";
import type { FormEvent } from "react";
import { useRouter } from "next/navigation";
import { ApiError, createBrand } from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Field, Input, Select, Textarea } from "@/components/ui/Input";
import { AuthSplitLayout } from "../auth-split-layout";

const CATEGORY_OPTIONS = ["Legal tech", "Fintech", "Healthcare", "D2C", "Other"];
const SECTOR_OPTIONS = ["B2B SaaS", "B2C", "Marketplace", "Other"];

export default function SignupBrandPage() {
  const { token } = useAuth();
  const { setSelectedBrandId, refresh } = useBrand();
  const router = useRouter();

  const [name, setName] = useState("");
  const [founded, setFounded] = useState("");
  const [category, setCategory] = useState(CATEGORY_OPTIONS[0]);
  const [sector, setSector] = useState(SECTOR_OPTIONS[0]);
  const [website, setWebsite] = useState("");
  const [oneLiner, setOneLiner] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState(false);

  async function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!token) return;
    if (!name.trim()) {
      setError("Brand name is required.");
      return;
    }

    setError(null);
    setIsSubmitting(true);
    try {
      // Brand (apps/api/models/brand.py) has no founded/sector/website/
      // one_liner columns — those are folded into product_catalog, the
      // one generic JSONB field it does have, rather than left client-side
      // only. industry doubles as "category" (a real Brand column).
      const brand = await createBrand(token, {
        name: name.trim(),
        industry: category,
        product_catalog: {
          founded: founded.trim() || null,
          sector,
          website: website.trim() || null,
          one_liner: oneLiner.trim() || null,
        },
      });
      await refresh();
      setSelectedBrandId(brand.id);
      router.push("/onboarding/interview");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to save your brand. Try again.");
    } finally {
      setIsSubmitting(false);
    }
  }

  return (
    <AuthSplitLayout>
      <div className="w-full max-w-[452px]">
        <div className="mb-2.5 flex items-center gap-2 text-[11.5px] font-bold tracking-[.12em] text-brand-600">
          STEP 2 OF 3 · ABOUT YOUR BRAND
        </div>
        <h1 className="mb-1.5 text-[31px] font-bold leading-[1.12] tracking-tight text-ink-950">
          The basics, only
        </h1>
        <p className="mb-6 text-sm text-ink-400">Just enough for Aarav to know what to ask next.</p>

        <form onSubmit={handleSubmit} noValidate className="space-y-3">
          {error ? (
            <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
              {error}
            </p>
          ) : null}

          <div className="grid grid-cols-[1.6fr_1fr] gap-3">
            <Field label="Brand name" htmlFor="brand-basics-name">
              <Input id="brand-basics-name" required value={name} onChange={(e) => setName(e.target.value)} />
            </Field>
            <Field label="Founded" htmlFor="brand-basics-founded">
              <Input
                id="brand-basics-founded"
                placeholder="2024"
                value={founded}
                onChange={(e) => setFounded(e.target.value)}
              />
            </Field>
          </div>

          <div className="grid grid-cols-2 gap-3">
            <Field label="Category" htmlFor="brand-basics-category">
              <Select id="brand-basics-category" value={category} onChange={(e) => setCategory(e.target.value)}>
                {CATEGORY_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </Field>
            <Field label="Sector" htmlFor="brand-basics-sector">
              <Select id="brand-basics-sector" value={sector} onChange={(e) => setSector(e.target.value)}>
                {SECTOR_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </Select>
            </Field>
          </div>

          <Field label="Website" htmlFor="brand-basics-website">
            <Input
              id="brand-basics-website"
              type="url"
              placeholder="https://example.com"
              value={website}
              onChange={(e) => setWebsite(e.target.value)}
            />
          </Field>

          <Field label="One line about what you do" htmlFor="brand-basics-one-liner">
            <Textarea
              id="brand-basics-one-liner"
              rows={3}
              value={oneLiner}
              onChange={(e) => setOneLiner(e.target.value)}
            />
          </Field>

          <div className="mb-1 mt-4 flex items-center gap-2.5 rounded-xl border border-brand-200 bg-brand-50 px-3.5 py-2.5">
            <div className="h-[26px] w-[26px] shrink-0 rounded-full bg-gradient-to-br from-brand-600 to-brand-200" />
            <p className="text-[12.5px] leading-snug text-ink-700">
              Aarav will read your site and ask the rest — you won&apos;t re-type any of this again.
            </p>
          </div>

          <div className="flex gap-2.5 pt-1">
            <Button type="button" variant="outline" onClick={() => router.push("/signup")}>
              Back
            </Button>
            <Button type="submit" className="flex-1" isLoading={isSubmitting}>
              Meet Aarav
            </Button>
          </div>
        </form>
      </div>
    </AuthSplitLayout>
  );
}
