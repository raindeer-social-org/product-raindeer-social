"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  connectLinkedIn,
  disconnectSocialAccount,
  fetchSocialAccounts,
  type AuthorizeUrlResponse,
  type SocialAccount,
  type SocialPlatform,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { useToast } from "@/components/ui/Toast";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Modal } from "@/components/ui/Modal";
import { redirectToAuthorizeUrl } from "./redirect";

// Human-readable labels per apps/api/models/social_account.py::SocialPlatform.
const PLATFORM_LABELS: Partial<Record<SocialPlatform, string>> = {
  linkedin: "LinkedIn",
};

function platformLabel(platform: SocialPlatform): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

// Platforms the UI can start a real connect flow for. LinkedIn is the only
// one with a working backend OAuth provider today — kept as a list plus a
// lookup table (not a single hardcoded button/handler) so a second real
// provider is a data change here, not a rewrite of this panel.
const CONNECTABLE_PLATFORMS: SocialPlatform[] = ["linkedin"];

const CONNECT_HANDLERS: Partial<
  Record<SocialPlatform, (token: string, brandId: string) => Promise<AuthorizeUrlResponse>>
> = {
  linkedin: connectLinkedIn,
};

// Platforms shown for parity with the design mockup's full distribution
// picture, but with no real connect flow behind them yet:
//   - X: OAuth/PKCE work exists on a separate, not-yet-merged branch — not
//     part of this codebase yet, so wiring a button here would either
//     duplicate that work or fake it. Left as "Coming soon".
//   - Instagram / Threads / Facebook: backend providers are landing in a
//     separate open PR (#118) — not merged, so nothing real to call yet.
//   - YouTube: no backend work has started.
// None of these render a working button — only a disabled "Coming soon"
// pill — so nothing here pretends to be more connected than it is.
const COMING_SOON_PLATFORMS: { key: string; name: string; initial: string; className: string }[] = [
  { key: "x", name: "X", initial: "X", className: "bg-ink-950" },
  { key: "instagram", name: "Instagram", initial: "IG", className: "bg-gradient-to-br from-[#F58529] via-[#DD2A7B] to-[#8134AF]" },
  { key: "threads", name: "Threads", initial: "@", className: "bg-ink-800" },
  { key: "facebook", name: "Facebook", initial: "f", className: "bg-[#1877F2]" },
  { key: "youtube", name: "YouTube", initial: "YT", className: "bg-[#FF0000]" },
];

function formatExpiry(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * The full "connect where you publish" list — real LinkedIn connect/
 * disconnect plus visible-but-inert rows for platforms with no backend
 * yet. Shared between the standalone Connections settings page
 * (app/social-accounts/page.tsx) and the finishing step of the Aarav
 * onboarding wizard (app/onboarding/interview/page.tsx) — Issue #123 asks
 * for the same content, restyled, in both places, so the logic and
 * markup live here once.
 */
export function SocialConnectionsPanel({
  onAnyConnected,
}: {
  /** Fires once, right after any platform's account list has loaded, with whether at least one account is active. */
  onAnyConnected?: (hasActive: boolean) => void;
}) {
  const { token } = useAuth();
  const { selectedBrandId } = useBrand();
  const { push } = useToast();

  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [connectingPlatform, setConnectingPlatform] = useState<SocialPlatform | null>(null);
  const [notConfiguredPlatform, setNotConfiguredPlatform] = useState<SocialPlatform | null>(null);
  const [pendingDisconnect, setPendingDisconnect] = useState<SocialAccount | null>(null);
  const [isDisconnecting, setIsDisconnecting] = useState(false);

  const loadAccounts = useCallback(
    async (showSpinner: boolean) => {
      if (!token || !selectedBrandId) {
        setAccounts([]);
        return;
      }
      if (showSpinner) setIsLoading(true);
      setLoadError(null);
      try {
        const result = await fetchSocialAccounts(token, selectedBrandId);
        setAccounts(result);
        onAnyConnected?.(result.some((account) => account.status === "active"));
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Failed to load social accounts");
      } finally {
        if (showSpinner) setIsLoading(false);
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps -- onAnyConnected is a callback, not reactive state
    [token, selectedBrandId]
  );

  // Re-run whenever the token or selected brand changes, and refresh on
  // window focus — the OAuth flow this page kicks off navigates away from
  // the app entirely, so a background refresh on return is the only way a
  // newly connected account shows up without a manual reload.
  useEffect(() => {
    setAccounts([]);
    loadAccounts(true);

    const onFocus = () => loadAccounts(false);
    window.addEventListener("focus", onFocus);
    return () => window.removeEventListener("focus", onFocus);
  }, [loadAccounts]);

  async function handleConnect(platform: SocialPlatform) {
    if (!token || !selectedBrandId) return;
    const connect = CONNECT_HANDLERS[platform];
    if (!connect) return;

    setNotConfiguredPlatform(null);
    setConnectingPlatform(platform);
    try {
      const { authorize_url } = await connect(token, selectedBrandId);
      redirectToAuthorizeUrl(authorize_url);
    } catch (err) {
      // The backend 503s with a specific, well-known detail message when
      // it has no LINKEDIN_REDIRECT_URI configured (see
      // apps/api/routers/social_accounts.py::connect_linkedin) — that's an
      // expected, common dev-environment state, not a generic failure, so
      // it gets its own friendly message instead of an error toast.
      if (err instanceof ApiError && err.status === 503) {
        setNotConfiguredPlatform(platform);
      } else {
        push(err instanceof ApiError ? err.message : "Failed to start the connection", "error");
      }
    } finally {
      setConnectingPlatform(null);
    }
  }

  async function handleDisconnect() {
    if (!token || !selectedBrandId || !pendingDisconnect) return;
    setIsDisconnecting(true);
    try {
      const updated = await disconnectSocialAccount(token, selectedBrandId, pendingDisconnect.id);
      setAccounts((current) => current.map((account) => (account.id === updated.id ? updated : account)));
      push(`Disconnected ${platformLabel(updated.platform)}`, "success");
      setPendingDisconnect(null);
    } catch (err) {
      push(err instanceof ApiError ? err.message : "Failed to disconnect account", "error");
    } finally {
      setIsDisconnecting(false);
    }
  }

  if (isLoading && accounts.length === 0) {
    return (
      <div className="space-y-3 rounded-2xl border border-line-soft bg-white p-5">
        <Skeleton className="h-5 w-1/3" />
        <Skeleton className="h-5 w-1/2" />
        <Skeleton className="h-5 w-1/4" />
      </div>
    );
  }

  return (
    <div className="space-y-4">
      {loadError ? (
        <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
          {loadError}
        </p>
      ) : null}

      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {CONNECTABLE_PLATFORMS.map((platform) => {
          const account = accounts.find((a) => a.platform === platform);
          const expiry = account ? formatExpiry(account.token_expires_at) : null;
          return (
            <div
              key={platform}
              className="flex items-center gap-3.5 rounded-2xl border border-line bg-white p-4"
            >
              <div className="flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[11px] bg-[#0A66C2] text-sm font-extrabold text-white">
                in
              </div>
              <div className="min-w-0 flex-1">
                <div className="text-sm font-bold text-ink-950">{platformLabel(platform)}</div>
                <div className="text-xs text-ink-300">
                  {account?.status === "active"
                    ? account.external_account_id
                      ? `Connected · ${account.external_account_id}`
                      : "Connected"
                    : account?.status === "expired"
                      ? expiry
                        ? `Expired ${expiry}`
                        : "Expired"
                      : account?.status === "revoked"
                        ? "Revoked"
                        : "Not connected"}
                </div>
                {notConfiguredPlatform === platform ? (
                  <p role="alert" className="mt-1 text-xs text-warning">
                    Not configured on this server yet.
                  </p>
                ) : null}
              </div>
              {account?.status === "active" ? (
                <Button
                  variant="danger"
                  size="sm"
                  onClick={() => setPendingDisconnect(account)}
                >
                  Disconnect
                </Button>
              ) : (
                <Button
                  variant="primary"
                  size="sm"
                  isLoading={connectingPlatform === platform}
                  onClick={() => handleConnect(platform)}
                >
                  {account ? "Reconnect" : "Connect"}
                </Button>
              )}
            </div>
          );
        })}

        {COMING_SOON_PLATFORMS.map((platform) => (
          <div
            key={platform.key}
            className="flex items-center gap-3.5 rounded-2xl border border-line bg-white p-4 opacity-70"
          >
            <div
              className={`flex h-[38px] w-[38px] shrink-0 items-center justify-center rounded-[11px] text-sm font-extrabold text-white ${platform.className}`}
            >
              {platform.initial}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-sm font-bold text-ink-950">{platform.name}</div>
              <div className="text-xs text-ink-300">Not yet available</div>
            </div>
            <Badge tone="slate">Coming soon</Badge>
          </div>
        ))}
      </div>

      {accounts.length === 0 && !isLoading ? (
        <EmptyState
          title="No accounts connected"
          description="Connect a platform above to start publishing from this brand."
        />
      ) : null}

      <Modal
        open={pendingDisconnect !== null}
        onClose={() => setPendingDisconnect(null)}
        title="Disconnect account"
        footer={
          <>
            <Button variant="outline" onClick={() => setPendingDisconnect(null)} disabled={isDisconnecting}>
              Cancel
            </Button>
            <Button variant="danger" isLoading={isDisconnecting} onClick={handleDisconnect}>
              Disconnect
            </Button>
          </>
        }
      >
        {pendingDisconnect ? (
          <p className="text-sm text-ink-600">
            Disconnect {platformLabel(pendingDisconnect.platform)}? Raindeer will no longer be able to
            publish to this account until it&apos;s reconnected.
          </p>
        ) : null}
      </Modal>
    </div>
  );
}
