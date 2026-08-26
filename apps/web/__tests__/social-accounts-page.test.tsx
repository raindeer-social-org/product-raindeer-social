import { describe, expect, it, vi, beforeEach } from "vitest";
import { act, render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import SocialAccountsPage from "@/app/social-accounts/page";
import { AuthProvider } from "@/lib/auth-context";
import { BrandProvider } from "@/lib/brand-context";
import { ToastProvider } from "@/components/ui/Toast";
import { ApiError } from "@/lib/api";
import type { SocialAccount } from "@/lib/api";

const fetchBrandsMock = vi.fn();
const fetchSocialAccountsMock = vi.fn();
const connectLinkedInMock = vi.fn();
const disconnectSocialAccountMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchSocialAccounts: (...args: unknown[]) => fetchSocialAccountsMock(...args),
    connectLinkedIn: (...args: unknown[]) => connectLinkedInMock(...args),
    disconnectSocialAccount: (...args: unknown[]) => disconnectSocialAccountMock(...args),
  };
});

const redirectToAuthorizeUrlMock = vi.fn();
vi.mock("@/app/social-accounts/redirect", () => ({
  redirectToAuthorizeUrl: (...args: unknown[]) => redirectToAuthorizeUrlMock(...args),
}));

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

function renderPage() {
  return render(
    <ToastProvider>
      <AuthProvider>
        <BrandProvider>
          <SocialAccountsPage />
        </BrandProvider>
      </AuthProvider>
    </ToastProvider>
  );
}

describe("SocialAccountsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchSocialAccountsMock.mockReset();
    connectLinkedInMock.mockReset();
    disconnectSocialAccountMock.mockReset();
    redirectToAuthorizeUrlMock.mockReset();

    window.localStorage.clear();
    window.localStorage.setItem("raindeer.auth.token", "test-token");

    fetchBrandsMock.mockResolvedValue(BRANDS);
    fetchSocialAccountsMock.mockResolvedValue([]);
  });

  it("renders connected accounts with a status badge per account", async () => {
    fetchSocialAccountsMock.mockResolvedValue([
      makeAccount({ id: "a1", status: "active" }),
      makeAccount({ id: "a2", status: "expired", external_account_id: "urn:li:person:456" }),
      makeAccount({ id: "a3", status: "revoked", external_account_id: null, token_expires_at: null }),
    ]);

    renderPage();

    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalledWith("test-token", "brand-1"));

    expect(await screen.findByText("Active")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();
    expect(screen.getByText("Account ID: urn:li:person:123")).toBeInTheDocument();
    expect(screen.getByText("No account ID on file")).toBeInTheDocument();
  });

  it("shows an empty state when nothing is connected for the brand", async () => {
    renderPage();

    expect(await screen.findByText("No accounts connected")).toBeInTheDocument();
  });

  it("starts the LinkedIn OAuth flow and redirects to the authorize URL on success", async () => {
    connectLinkedInMock.mockResolvedValue({
      authorize_url: "https://www.linkedin.com/oauth/v2/authorization?foo=bar",
    });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "Connect LinkedIn" }));

    await waitFor(() => {
      expect(connectLinkedInMock).toHaveBeenCalledWith("test-token", "brand-1");
      expect(redirectToAuthorizeUrlMock).toHaveBeenCalledWith(
        "https://www.linkedin.com/oauth/v2/authorization?foo=bar"
      );
    });
  });

  it("shows a friendly message instead of a generic error when LinkedIn isn't configured", async () => {
    connectLinkedInMock.mockRejectedValue(new ApiError("LinkedIn OAuth is not configured", 503));
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalled());

    await user.click(screen.getByRole("button", { name: "Connect LinkedIn" }));

    expect(await screen.findByText("LinkedIn isn't configured on this server yet.")).toBeInTheDocument();
    expect(redirectToAuthorizeUrlMock).not.toHaveBeenCalled();
    // Not a raw/generic backend error message anywhere on the page.
    expect(screen.queryByText("LinkedIn OAuth is not configured")).not.toBeInTheDocument();
  });

  it("disconnects an account only after the confirmation step is completed", async () => {
    fetchSocialAccountsMock.mockResolvedValue([makeAccount({ id: "a1", status: "active" })]);
    disconnectSocialAccountMock.mockResolvedValue(makeAccount({ id: "a1", status: "revoked" }));
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Active");

    await user.click(screen.getByRole("button", { name: "Disconnect" }));

    // Confirmation dialog is open; the API call hasn't fired yet.
    const dialog = await screen.findByRole("dialog");
    expect(disconnectSocialAccountMock).not.toHaveBeenCalled();

    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    });

    await waitFor(() => {
      expect(disconnectSocialAccountMock).toHaveBeenCalledWith("test-token", "brand-1", "a1");
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText("Revoked")).toBeInTheDocument();
  });

  it("cancels the disconnect confirmation without calling the API", async () => {
    fetchSocialAccountsMock.mockResolvedValue([makeAccount({ id: "a1", status: "active" })]);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Active");

    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(disconnectSocialAccountMock).not.toHaveBeenCalled();
    expect(screen.getByText("Active")).toBeInTheDocument();
  });
});
