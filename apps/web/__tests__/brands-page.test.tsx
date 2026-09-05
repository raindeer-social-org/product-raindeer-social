import { describe, expect, it, vi, beforeEach, afterEach } from "vitest";
import { act, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import BrandsPage from "@/app/brands/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { Brand } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const createBrandMock = vi.fn();
const updateBrandMock = vi.fn();
const deleteBrandMock = vi.fn();
const uploadBrandLogoMock = vi.fn();
const removeBrandLogoMock = vi.fn();
const exportBrandReportMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    createBrand: (...args: unknown[]) => createBrandMock(...args),
    updateBrand: (...args: unknown[]) => updateBrandMock(...args),
    deleteBrand: (...args: unknown[]) => deleteBrandMock(...args),
    uploadBrandLogo: (...args: unknown[]) => uploadBrandLogoMock(...args),
    removeBrandLogo: (...args: unknown[]) => removeBrandLogoMock(...args),
    exportBrandReport: (...args: unknown[]) => exportBrandReportMock(...args),
  };
});

const routerPush = vi.fn();
vi.mock("next/navigation", () => ({
  useRouter: () => ({ push: routerPush }),
}));

function makeBrand(overrides: Partial<Brand> = {}): Brand {
  return {
    id: "brand-1",
    organization_id: "org-1",
    name: "Acme Co",
    industry: "Retail",
    logo_url: null,
    target_audience: "Young professionals",
    colors: ["#FF5733", "#1A1A2E"],
    tone_descriptors: ["playful", "confident"],
    product_catalog: null,
    brand_report: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <BrandsPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("BrandsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    createBrandMock.mockReset();
    updateBrandMock.mockReset();
    deleteBrandMock.mockReset();
    uploadBrandLogoMock.mockReset();
    removeBrandLogoMock.mockReset();
    exportBrandReportMock.mockReset();
    routerPush.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("renders every brand as a card with its industry, audience, and color swatches", async () => {
    fetchBrandsMock.mockResolvedValue([makeBrand()]);

    renderPage();

    const card = await screen.findByRole("article", { name: "Acme Co" });
    expect(within(card).getByText("Retail")).toBeInTheDocument();
    expect(within(card).getByText("Young professionals")).toBeInTheDocument();
    expect(within(card).getByText("playful")).toBeInTheDocument();
    expect(within(card).getByTitle("#FF5733")).toBeInTheDocument();
  });

  it("shows an empty state with a create CTA when the org has no brands", async () => {
    fetchBrandsMock.mockResolvedValue([]);

    renderPage();

    await screen.findByText("No brands yet");
    expect(screen.getByRole("button", { name: "Create your first brand" })).toBeInTheDocument();
  });

  it("creates a new brand through the form and refreshes the list", async () => {
    fetchBrandsMock.mockResolvedValueOnce([]).mockResolvedValueOnce([makeBrand({ id: "new-1", name: "New Brand" })]);
    createBrandMock.mockResolvedValue(makeBrand({ id: "new-1", name: "New Brand" }));
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("No brands yet");

    await user.click(screen.getByRole("button", { name: "Create your first brand" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "New brand" })).toBeInTheDocument();

    await user.type(within(dialog).getByLabelText("Name", { exact: false }), "New Brand");
    await user.type(within(dialog).getByLabelText("Industry"), "Tech");
    await user.type(within(dialog).getByLabelText(/Brand colors/), "#111111, #222222");
    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Create brand" }));
    });

    await waitFor(() => {
      expect(createBrandMock).toHaveBeenCalledWith(
        "test-token",
        expect.objectContaining({
          name: "New Brand",
          industry: "Tech",
          colors: ["#111111", "#222222"],
        })
      );
    });

    expect(fetchBrandsMock).toHaveBeenCalledTimes(2);
    await screen.findByRole("article", { name: "New Brand" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("rejects invalid JSON in the product catalog field without submitting", async () => {
    fetchBrandsMock.mockResolvedValue([]);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("No brands yet");
    await user.click(screen.getByRole("button", { name: "Create your first brand" }));
    const dialog = await screen.findByRole("dialog");

    await user.type(within(dialog).getByLabelText("Name", { exact: false }), "Bad JSON Brand");
    // fireEvent.change (not user.type) — userEvent.type() treats "{"/"}" as
    // special-key syntax, so a raw invalid-JSON string can't be typed with it.
    fireEvent.change(within(dialog).getByLabelText(/Product catalog/), {
      target: { value: "{not valid json" },
    });
    await user.click(within(dialog).getByRole("button", { name: "Create brand" }));

    expect(await within(dialog).findByRole("alert")).toHaveTextContent(/valid JSON/);
    expect(createBrandMock).not.toHaveBeenCalled();
  });

  it("edits an existing brand, pre-filling the form, and round-trips it through the API", async () => {
    fetchBrandsMock
      .mockResolvedValueOnce([makeBrand()])
      .mockResolvedValueOnce([makeBrand({ industry: "Fashion" })]);
    updateBrandMock.mockResolvedValue(makeBrand({ industry: "Fashion" }));
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });

    await user.click(within(card).getByRole("button", { name: "Edit" }));
    const dialog = await screen.findByRole("dialog");
    expect(within(dialog).getByRole("heading", { name: "Edit brand" })).toBeInTheDocument();
    expect(within(dialog).getByLabelText("Name", { exact: false })).toHaveValue("Acme Co");
    expect(within(dialog).getByLabelText("Industry")).toHaveValue("Retail");

    await user.clear(within(dialog).getByLabelText("Industry"));
    await user.type(within(dialog).getByLabelText("Industry"), "Fashion");
    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Save changes" }));
    });

    await waitFor(() => {
      expect(updateBrandMock).toHaveBeenCalledWith(
        "test-token",
        "brand-1",
        expect.objectContaining({ industry: "Fashion" })
      );
    });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
  });

  it("deletes a brand after confirmation and removes it from the list", async () => {
    fetchBrandsMock.mockResolvedValueOnce([makeBrand()]).mockResolvedValueOnce([]);
    deleteBrandMock.mockResolvedValue(undefined);
    vi.spyOn(window, "confirm").mockReturnValue(true);
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });

    await act(async () => {
      await user.click(within(card).getByRole("button", { name: "Delete" }));
    });

    expect(window.confirm).toHaveBeenCalledWith(expect.stringContaining("Acme Co"));
    await waitFor(() => expect(deleteBrandMock).toHaveBeenCalledWith("test-token", "brand-1"));
    await waitFor(() => expect(screen.queryByRole("article", { name: "Acme Co" })).not.toBeInTheDocument());
  });

  it("does not delete a brand when the confirmation is dismissed", async () => {
    fetchBrandsMock.mockResolvedValue([makeBrand()]);
    vi.spyOn(window, "confirm").mockReturnValue(false);
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });
    await user.click(within(card).getByRole("button", { name: "Delete" }));

    expect(deleteBrandMock).not.toHaveBeenCalled();
    expect(screen.getByRole("article", { name: "Acme Co" })).toBeInTheDocument();
  });

  it("uploads a logo from the edit modal and refreshes the brand list", async () => {
    fetchBrandsMock
      .mockResolvedValueOnce([makeBrand()])
      .mockResolvedValueOnce([makeBrand({ logo_url: "https://cdn.example.com/logo.png" })]);
    uploadBrandLogoMock.mockResolvedValue(makeBrand({ logo_url: "https://cdn.example.com/logo.png" }));
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });
    await user.click(within(card).getByRole("button", { name: "Edit" }));

    const dialog = await screen.findByRole("dialog");
    const file = new File(["logo-bytes"], "logo.png", { type: "image/png" });
    const fileInput = within(dialog).getByLabelText("Upload logo");

    await act(async () => {
      await user.upload(fileInput, file);
    });

    await waitFor(() => {
      expect(uploadBrandLogoMock).toHaveBeenCalledWith("test-token", "brand-1", file);
    });
    expect(fetchBrandsMock).toHaveBeenCalledTimes(2);
  });

  it("renders Voice/Audience/Products tag chips sourced from the real Brand fields", async () => {
    fetchBrandsMock.mockResolvedValue([
      makeBrand({
        target_audience: "Early-stage founders, Startup CFOs",
        product_catalog: { products: ["Contract review", { name: "Compliance monitor" }] },
      }),
    ]);

    renderPage();

    const card = await screen.findByRole("article", { name: "Acme Co" });
    expect(within(card).getByText("playful")).toBeInTheDocument(); // Voice, from tone_descriptors
    expect(within(card).getByText("Early-stage founders")).toBeInTheDocument(); // Audience, comma-split
    expect(within(card).getByText("Startup CFOs")).toBeInTheDocument();
    expect(within(card).getByText("Contract review")).toBeInTheDocument(); // Products, from product_catalog
    expect(within(card).getByText("Compliance monitor")).toBeInTheDocument();
  });

  it("exports the brand report PDF via the real exportBrandReport call and opens it", async () => {
    fetchBrandsMock.mockResolvedValue([makeBrand()]);
    exportBrandReportMock.mockResolvedValue({
      url: "https://cdn.example.com/report.pdf",
      generated_at: "2026-01-02T00:00:00Z",
    });
    const openSpy = vi.spyOn(window, "open").mockImplementation(() => null);
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });

    await act(async () => {
      await user.click(within(card).getByRole("button", { name: "Export brand PDF" }));
    });

    await waitFor(() => expect(exportBrandReportMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(openSpy).toHaveBeenCalledWith("https://cdn.example.com/report.pdf", "_blank", "noopener,noreferrer");
  });

  it("navigates to onboarding when re-interviewing with Aarav", async () => {
    fetchBrandsMock.mockResolvedValue([makeBrand()]);
    const user = userEvent.setup();

    renderPage();
    const card = await screen.findByRole("article", { name: "Acme Co" });

    await user.click(within(card).getByRole("button", { name: "Re-interview with Aarav" }));

    expect(routerPush).toHaveBeenCalledWith("/onboarding");
  });
});
