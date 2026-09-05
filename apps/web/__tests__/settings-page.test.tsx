import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SettingsPage from "@/app/settings/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import type { BrandSettings, SocialAccount } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchSocialAccountsMock = vi.fn();
const fetchBrandSettingsMock = vi.fn();
const updateBrandSettingsMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchSocialAccounts: (...args: unknown[]) => fetchSocialAccountsMock(...args),
    fetchBrandSettings: (...args: unknown[]) => fetchBrandSettingsMock(...args),
    updateBrandSettings: (...args: unknown[]) => updateBrandSettingsMock(...args),
  };
});

const BRANDS = [
  {
    id: "brand-1",
    organization_id: "org-1",
    name: "Acme Co",
    industry: null,
    logo_url: null,
    target_audience: null,
    colors: null,
    tone_descriptors: null,
    product_catalog: null,
    brand_report: null,
    created_at: "2026-01-01",
    updated_at: "2026-01-01",
  },
];

function makeAccount(overrides: Partial<SocialAccount> = {}): SocialAccount {
  return {
    id: "account-1",
    brand_id: "brand-1",
    platform: "linkedin",
    external_account_id: "urn:li:person:123",
    token_expires_at: "2026-09-01T00:00:00Z",
    scopes: ["w_member_social"],
    status: "active",
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function makeSettings(overrides: Partial<BrandSettings> = {}): BrandSettings {
  return {
    id: "settings-1",
    brand_id: "brand-1",
    auto_approve_enabled: false,
    auto_approve_threshold: 90,
    show_agent_reasoning: true,
    email_review_digest_enabled: true,
    auto_shift_posting_times: true,
    created_at: "2026-08-01T00:00:00Z",
    updated_at: "2026-08-01T00:00:00Z",
    ...overrides,
  };
}

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <SettingsPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("SettingsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchSocialAccountsMock.mockReset();
    fetchBrandSettingsMock.mockReset();
    updateBrandSettingsMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchSocialAccountsMock.mockResolvedValue([]);
    fetchBrandSettingsMock.mockResolvedValue(makeSettings());
  });

  it("renders connected channels reusing the real fetchSocialAccounts data", async () => {
    fetchSocialAccountsMock.mockResolvedValue([makeAccount()]);

    renderPage();

    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalledWith("test-token", "brand-1"));
    expect(await screen.findByText("LinkedIn")).toBeInTheDocument();
    expect(screen.getByText("Connected")).toBeInTheDocument();
  });

  it("shows an empty state when no channels are connected", async () => {
    fetchSocialAccountsMock.mockResolvedValue([]);

    renderPage();

    expect(await screen.findByText("No channels connected")).toBeInTheDocument();
  });

  it("loads and renders the agent-behaviour toggles from real settings", async () => {
    renderPage();

    await waitFor(() => expect(fetchBrandSettingsMock).toHaveBeenCalledWith("test-token", "brand-1"));

    const reasoningSwitch = await screen.findByRole("switch", { name: "Show agent reasoning in the Arena" });
    expect(reasoningSwitch).toHaveAttribute("aria-checked", "true");

    const autoApproveSwitch = screen.getByRole("switch", { name: "Auto-approve posts above the score threshold" });
    expect(autoApproveSwitch).toHaveAttribute("aria-checked", "false");
    // Threshold input only shows once auto-approve is enabled.
    expect(screen.queryByLabelText("Score threshold")).not.toBeInTheDocument();
  });

  it("toggles a switch and persists it through updateBrandSettings", async () => {
    updateBrandSettingsMock.mockResolvedValue(makeSettings({ show_agent_reasoning: false }));
    const user = userEvent.setup();

    renderPage();
    const reasoningSwitch = await screen.findByRole("switch", { name: "Show agent reasoning in the Arena" });

    await act(async () => {
      await user.click(reasoningSwitch);
    });

    await waitFor(() => {
      expect(updateBrandSettingsMock).toHaveBeenCalledWith("test-token", "brand-1", {
        show_agent_reasoning: false,
      });
    });
    expect(reasoningSwitch).toHaveAttribute("aria-checked", "false");
  });

  it("reveals and saves the auto-approve threshold once auto-approve is enabled", async () => {
    updateBrandSettingsMock
      .mockResolvedValueOnce(makeSettings({ auto_approve_enabled: true }))
      .mockResolvedValueOnce(makeSettings({ auto_approve_enabled: true, auto_approve_threshold: 75 }));
    const user = userEvent.setup();

    renderPage();
    const autoApproveSwitch = await screen.findByRole("switch", {
      name: "Auto-approve posts above the score threshold",
    });

    await act(async () => {
      await user.click(autoApproveSwitch);
    });

    const thresholdInput = await screen.findByLabelText("Score threshold");
    await user.clear(thresholdInput);
    await user.type(thresholdInput, "75");
    await act(async () => {
      thresholdInput.blur();
    });

    await waitFor(() => {
      expect(updateBrandSettingsMock).toHaveBeenCalledWith("test-token", "brand-1", {
        auto_approve_threshold: 75,
      });
    });
  });

  it("reverts the toggle and shows an error toast when saving fails", async () => {
    updateBrandSettingsMock.mockRejectedValue(new Error("Failed to save this setting"));
    const user = userEvent.setup();

    renderPage();
    const reasoningSwitch = await screen.findByRole("switch", { name: "Show agent reasoning in the Arena" });

    await act(async () => {
      await user.click(reasoningSwitch);
    });

    await waitFor(() => expect(reasoningSwitch).toHaveAttribute("aria-checked", "true"));
    expect(await screen.findByText("Failed to save this setting")).toBeInTheDocument();
  });
});
