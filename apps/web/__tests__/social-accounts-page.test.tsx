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
const connectXMock = vi.fn();
const connectInstagramMock = vi.fn();
const connectThreadsMock = vi.fn();
const connectFacebookMock = vi.fn();
const connectYouTubeMock = vi.fn();
const connectTikTokMock = vi.fn();
const connectPinterestMock = vi.fn();
const disconnectSocialAccountMock = vi.fn();

vi.mock("@/lib/api", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api")>("@/lib/api");
  return {
    ...actual,
    fetchBrands: (...args: unknown[]) => fetchBrandsMock(...args),
    fetchSocialAccounts: (...args: unknown[]) => fetchSocialAccountsMock(...args),
    connectLinkedIn: (...args: unknown[]) => connectLinkedInMock(...args),
    connectX: (...args: unknown[]) => connectXMock(...args),
    connectInstagram: (...args: unknown[]) => connectInstagramMock(...args),
    connectThreads: (...args: unknown[]) => connectThreadsMock(...args),
    connectFacebook: (...args: unknown[]) => connectFacebookMock(...args),
    connectYouTube: (...args: unknown[]) => connectYouTubeMock(...args),
    connectTikTok: (...args: unknown[]) => connectTikTokMock(...args),
    connectPinterest: (...args: unknown[]) => connectPinterestMock(...args),
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

// Every platform this panel lists now has a real backend OAuth provider
// (apps/api/routers/social_accounts.py) — Issue #138 added YouTube/TikTok/
// Pinterest alongside the LinkedIn/X/Instagram/Threads/Facebook providers
// #91/#118/#121 already wired up. Nothing left to show as "coming soon".
const CONNECT_MOCKS = {
  LinkedIn: connectLinkedInMock,
  X: connectXMock,
  Instagram: connectInstagramMock,
  Threads: connectThreadsMock,
  Facebook: connectFacebookMock,
  YouTube: connectYouTubeMock,
  TikTok: connectTikTokMock,
  Pinterest: connectPinterestMock,
} as const;

describe("SocialAccountsPage", () => {
  beforeEach(() => {
    fetchBrandsMock.mockReset();
    fetchSocialAccountsMock.mockReset();
    for (const mock of Object.values(CONNECT_MOCKS)) mock.mockReset();
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
      makeAccount({
        id: "a2",
        platform: "instagram",
        status: "expired",
        external_account_id: "ig-456",
        token_expires_at: null,
      }),
      makeAccount({
        id: "a3",
        platform: "x",
        status: "revoked",
        external_account_id: null,
        token_expires_at: null,
      }),
    ]);

    renderPage();

    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalledWith("test-token", "brand-1"));

    expect(await screen.findByText("Connected · urn:li:person:123")).toBeInTheDocument();
    expect(screen.getByText("Expired")).toBeInTheDocument();
    expect(screen.getByText("Revoked")).toBeInTheDocument();

    // All 8 platforms are real now — none render as an inert "Coming soon" row.
    expect(screen.queryByText("Coming soon")).not.toBeInTheDocument();
    for (const label of Object.keys(CONNECT_MOCKS)) {
      // "X" matches both the platform name and its avatar badge initial, so
      // it's checked with getAllByText rather than the exact-one getByText.
      if (label === "X") {
        expect(screen.getAllByText("X").length).toBeGreaterThan(0);
      } else {
        expect(screen.getByText(label)).toBeInTheDocument();
      }
    }
  });

  it("shows LinkedIn as not connected when there's no account yet", async () => {
    renderPage();

    // Wait for the actual fetch chain (AuthProvider -> BrandProvider ->
    // this page's own fetchSocialAccounts) to settle before asserting —
    // see the identical fix in onboarding-page.test.tsx for why a bare
    // findByText can occasionally race a still-loading intermediate render.
    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalled());
    // Every platform is unconnected here, so "Not connected" renders once
    // per row — check the LinkedIn-specific connect button instead of the
    // (ambiguous, 8x-repeated) status text.
    expect(await screen.findByRole("button", { name: "Connect LinkedIn" })).toBeInTheDocument();
    expect(screen.getAllByText("Not connected").length).toBeGreaterThan(0);
  });

  it.each([
    ["LinkedIn", connectLinkedInMock, "https://www.linkedin.com/oauth/v2/authorization?foo=bar"],
    ["X", connectXMock, "https://twitter.com/i/oauth2/authorize?foo=bar"],
    ["Instagram", connectInstagramMock, "https://www.facebook.com/v21.0/dialog/oauth?foo=bar"],
    ["Threads", connectThreadsMock, "https://threads.net/oauth/authorize?foo=bar"],
    ["Facebook", connectFacebookMock, "https://www.facebook.com/v21.0/dialog/oauth?foo=bar"],
    ["YouTube", connectYouTubeMock, "https://accounts.google.com/o/oauth2/v2/auth?foo=bar"],
    ["TikTok", connectTikTokMock, "https://www.tiktok.com/v2/auth/authorize?foo=bar"],
    ["Pinterest", connectPinterestMock, "https://www.pinterest.com/oauth?foo=bar"],
  ])("starts the %s OAuth flow and redirects to the authorize URL on success", async (label, mock, authorizeUrl) => {
    mock.mockResolvedValue({ authorize_url: authorizeUrl });
    const user = userEvent.setup();

    renderPage();
    await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalled());

    await user.click(await screen.findByRole("button", { name: `Connect ${label}` }));

    await waitFor(() => {
      expect(mock).toHaveBeenCalledWith("test-token", "brand-1");
      expect(redirectToAuthorizeUrlMock).toHaveBeenCalledWith(authorizeUrl);
    });
  });

  it.each(Object.entries(CONNECT_MOCKS))(
    "shows a friendly message instead of a generic error when %s isn't configured",
    async (label, mock) => {
      mock.mockRejectedValue(new ApiError(`${label} OAuth is not configured`, 503));
      const user = userEvent.setup();

      renderPage();
      await waitFor(() => expect(fetchSocialAccountsMock).toHaveBeenCalled());

      await user.click(await screen.findByRole("button", { name: `Connect ${label}` }));

      expect(await screen.findByText("Not configured on this server yet.")).toBeInTheDocument();
      expect(redirectToAuthorizeUrlMock).not.toHaveBeenCalled();
      // Not a raw/generic backend error message anywhere on the page.
      expect(screen.queryByText(`${label} OAuth is not configured`)).not.toBeInTheDocument();
    }
  );

  it("disconnects an account only after the confirmation step is completed", async () => {
    fetchSocialAccountsMock.mockResolvedValue([makeAccount({ status: "active" })]);
    disconnectSocialAccountMock.mockResolvedValue(makeAccount({ status: "revoked" }));
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Connected · urn:li:person:123");

    await user.click(screen.getByRole("button", { name: "Disconnect" }));

    // Confirmation dialog is open; the API call hasn't fired yet.
    const dialog = await screen.findByRole("dialog");
    expect(disconnectSocialAccountMock).not.toHaveBeenCalled();

    await act(async () => {
      await user.click(within(dialog).getByRole("button", { name: "Disconnect" }));
    });

    await waitFor(() => {
      expect(disconnectSocialAccountMock).toHaveBeenCalledWith("test-token", "brand-1", "account-1");
    });
    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(await screen.findByText("Revoked")).toBeInTheDocument();
  });

  it("cancels the disconnect confirmation without calling the API", async () => {
    fetchSocialAccountsMock.mockResolvedValue([makeAccount({ status: "active" })]);
    const user = userEvent.setup();

    renderPage();
    await screen.findByText("Connected · urn:li:person:123");

    await user.click(screen.getByRole("button", { name: "Disconnect" }));
    const dialog = await screen.findByRole("dialog");
    await user.click(within(dialog).getByRole("button", { name: "Cancel" }));

    await waitFor(() => expect(screen.queryByRole("dialog")).not.toBeInTheDocument());
    expect(disconnectSocialAccountMock).not.toHaveBeenCalled();
    expect(screen.getByText("Connected · urn:li:person:123")).toBeInTheDocument();
  });
});
