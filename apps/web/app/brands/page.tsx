"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import {
  ApiError,
  type Brand,
  type BrandInput,
  type BrandUpdateInput,
  createBrand,
  deleteBrand,
  exportBrandReport,
  removeBrandLogo,
  updateBrand,
  uploadBrandLogo,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { Modal } from "@/components/ui/Modal";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { useToast } from "@/components/ui/Toast";
import { BrandCard } from "./brand-card";
import { BrandForm } from "./brand-form";

type ModalState = { mode: "create" } | { mode: "edit"; brandId: string } | null;

function IconBrand() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <path
        d="M4 20V6a2 2 0 012-2h8l6 6v10a2 2 0 01-2 2H6a2 2 0 01-2-2Z"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinejoin="round"
      />
      <path d="M14 4v5a1 1 0 001 1h5" stroke="currentColor" strokeWidth="1.8" strokeLinejoin="round" />
    </svg>
  );
}

function BrandCardSkeleton() {
  return (
    <Card className="p-5">
      <div className="flex items-center gap-3">
        <Skeleton className="h-12 w-12 rounded-full" />
        <div className="flex-1 space-y-2">
          <Skeleton className="h-4 w-2/3" />
          <Skeleton className="h-4 w-1/3" />
        </div>
      </div>
      <Skeleton className="mt-4 h-3 w-full" />
      <Skeleton className="mt-2 h-3 w-4/5" />
    </Card>
  );
}

export default function BrandsPage() {
  const { token } = useAuth();
  const { brands, isLoading, error, refresh, setSelectedBrandId } = useBrand();
  const { push } = useToast();
  const router = useRouter();
  const [modalState, setModalState] = useState<ModalState>(null);
  const [exportingBrandId, setExportingBrandId] = useState<string | null>(null);

  const editingBrand =
    modalState?.mode === "edit" ? brands.find((brand) => brand.id === modalState.brandId) ?? null : null;

  function openCreateModal() {
    setModalState({ mode: "create" });
  }

  function openEditModal(brand: Brand) {
    setModalState({ mode: "edit", brandId: brand.id });
  }

  function closeModal() {
    setModalState(null);
  }

  async function handleSubmit(payload: BrandInput | BrandUpdateInput) {
    if (!token || !modalState) return;
    if (modalState.mode === "edit") {
      await updateBrand(token, modalState.brandId, payload);
    } else {
      await createBrand(token, payload as BrandInput);
    }
    await refresh();
    push(modalState.mode === "edit" ? "Brand updated." : "Brand created.", "success");
    closeModal();
  }

  async function handleDelete(brand: Brand) {
    if (!token) return;
    const confirmed = window.confirm(`Delete "${brand.name}"? This cannot be undone.`);
    if (!confirmed) return;

    try {
      await deleteBrand(token, brand.id);
      await refresh();
      push("Brand deleted.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to delete brand.", "error");
    }
  }

  async function handleUploadLogo(brandId: string, file: File) {
    if (!token) return;
    try {
      await uploadBrandLogo(token, brandId, file);
      await refresh();
      push("Logo uploaded.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to upload logo.", "error");
    }
  }

  async function handleRemoveLogo(brandId: string) {
    if (!token) return;
    try {
      await removeBrandLogo(token, brandId);
      await refresh();
      push("Logo removed.", "success");
    } catch (err) {
      push(err instanceof Error ? err.message : "Failed to remove logo.", "error");
    }
  }

  // Reuses apps/web/app/onboarding/page.tsx's exact exportBrandReport call
  // rather than reimplementing it — same endpoint, same "open the PDF in a
  // new tab" behavior.
  async function handleExportPdf(brand: Brand) {
    if (!token) return;
    setExportingBrandId(brand.id);
    try {
      const result = await exportBrandReport(token, brand.id);
      if (typeof window !== "undefined") {
        window.open(result.url, "_blank", "noopener,noreferrer");
      }
      push("Brand report PDF ready.", "success");
    } catch (err) {
      push(err instanceof ApiError ? err.message : "Failed to export PDF report.", "error");
    } finally {
      setExportingBrandId(null);
    }
  }

  // /onboarding acts on whichever brand is selected in the BrandSwitcher,
  // not a per-brand URL — re-interviewing brand X from its own card has to
  // select it first so the onboarding page it lands on is actually X's.
  //
  // TODO(#123): once the dedicated Aarav interview flow lands, point this
  // at that page instead of the general onboarding questionnaire.
  function handleReinterview(brand: Brand) {
    setSelectedBrandId(brand.id);
    router.push("/onboarding");
  }

  return (
    <div>
      <PageHeader
        title="Brands"
        description="Manage the brands your organization runs content for."
        action={<Button onClick={openCreateModal}>+ New brand</Button>}
      />

      {error ? (
        <p role="alert" className="mb-4 rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
          {error}
        </p>
      ) : null}

      {isLoading && brands.length === 0 ? (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          <BrandCardSkeleton />
          <BrandCardSkeleton />
          <BrandCardSkeleton />
        </div>
      ) : brands.length === 0 ? (
        <EmptyState
          icon={<IconBrand />}
          title="No brands yet"
          description="Create your first brand to start planning and publishing content for it."
          action={<Button onClick={openCreateModal}>Create your first brand</Button>}
        />
      ) : (
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {brands.map((brand) => (
            <BrandCard
              key={brand.id}
              brand={brand}
              onEdit={() => openEditModal(brand)}
              onDelete={() => handleDelete(brand)}
              onExportPdf={() => handleExportPdf(brand)}
              onReinterview={() => handleReinterview(brand)}
              isExporting={exportingBrandId === brand.id}
            />
          ))}
        </div>
      )}

      <Modal
        open={modalState !== null}
        onClose={closeModal}
        title={modalState?.mode === "edit" ? "Edit brand" : "New brand"}
        size="lg"
      >
        {modalState !== null ? (
          <BrandForm
            brand={editingBrand}
            onCancel={closeModal}
            onSubmit={handleSubmit}
            onUploadLogo={editingBrand ? (file) => handleUploadLogo(editingBrand.id, file) : undefined}
            onRemoveLogo={editingBrand ? () => handleRemoveLogo(editingBrand.id) : undefined}
          />
        ) : null}
      </Modal>
    </div>
  );
}
