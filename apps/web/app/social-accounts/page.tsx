"use client";

import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  connectFacebook,
  connectInstagram,
  connectLinkedIn,
  connectPinterest,
  connectThreads,
  connectTikTok,
  connectYouTube,
  disconnectSocialAccount,
  fetchSocialAccounts,
  type AuthorizeUrlResponse,
  type SocialAccount,
  type SocialAccountStatus,
  type SocialPlatform,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { useToast } from "@/components/ui/Toast";
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { Modal } from "@/components/ui/Modal";
import { redirectToAuthorizeUrl } from "./redirect";

// Human-readable labels per apps/api/models/social_account.py::SocialPlatform.
// Falls back to the raw value for anything not listed, so an unrecognized
// platform still renders instead of breaking.
const PLATFORM_LABELS: Partial<Record<SocialPlatform, string>> = {
  linkedin: "LinkedIn",
  instagram: "Instagram",
  threads: "Threads",
  facebook: "Facebook",
  youtube: "YouTube",
  tiktok: "TikTok",
  pinterest: "Pinterest",
};

function platformLabel(platform: SocialPlatform): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

// Platforms the UI can start a connect flow for — a list plus a lookup
// table (not a hardcoded button/handler per platform) so adding another
// provider is a data change here rather than a rewrite of this page.
// Every platform below (Issue #138) is independently connectable; whether
// it actually works depends on the corresponding *_REDIRECT_URI env var
// being configured server-side (unconfigured ones 503, handled below).
const CONNECTABLE_PLATFORMS: SocialPlatform[] = [
  "linkedin",
  "instagram",
  "threads",
  "facebook",
  "youtube",
  "tiktok",
  "pinterest",
];

const CONNECT_HANDLERS: Partial<
  Record<SocialPlatform, (token: string, brandId: string) => Promise<AuthorizeUrlResponse>>
> = {
  linkedin: connectLinkedIn,
  instagram: connectInstagram,
  threads: connectThreads,
  facebook: connectFacebook,
  youtube: connectYouTube,
  tiktok: connectTikTok,
  pinterest: connectPinterest,
};

const STATUS_TONE: Record<SocialAccountStatus, BadgeTone> = {
  active: "green",
  expired: "amber",
  revoked: "slate",
};

const STATUS_LABEL: Record<SocialAccountStatus, string> = {
  active: "Active",
  expired: "Expired",
  revoked: "Revoked",
};

function formatExpiry(iso: string | null): string | null {
  if (!iso) return null;
  const date = new Date(iso);
  if (Number.isNaN(date.getTime())) return null;
  return date.toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export default function SocialAccountsPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
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
      } catch (err) {
        setLoadError(err instanceof Error ? err.message : "Failed to load social accounts");
      } finally {
        if (showSpinner) setIsLoading(false);
      }
    },
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

  return (
    <div>
      <PageHeader
        title="Connections"
        description={
          selectedBrand
            ? `Social accounts connected for ${selectedBrand.name}.`
            : "Select a brand to manage its social account connections."
        }
      />

      {!selectedBrand ? (
        <EmptyState title="No brand selected" description="Choose a brand to see its connections." />
      ) : (
        <div className="space-y-6">
          <Card>
            <CardHeader
              title="Connect a platform"
              description="Starts the OAuth flow in this tab and brings you back here once it's authorized."
            />
            <CardBody className="flex flex-wrap gap-4">
              {CONNECTABLE_PLATFORMS.map((platform) => (
                <div key={platform} className="flex flex-col gap-1.5">
                  <Button
                    variant="primary"
                    isLoading={connectingPlatform === platform}
                    onClick={() => handleConnect(platform)}
                  >
                    Connect {platformLabel(platform)}
                  </Button>
                  {notConfiguredPlatform === platform ? (
                    <p role="alert" className="max-w-xs text-sm text-amber-700">
                      {platformLabel(platform)} isn&apos;t configured on this server yet.
                    </p>
                  ) : null}
                </div>
              ))}
            </CardBody>
          </Card>

          {loadError ? (
            <p role="alert" className="rounded-lg bg-red-50 px-3 py-2 text-sm font-medium text-red-700">
              {loadError}
            </p>
          ) : null}

          {isLoading && accounts.length === 0 ? (
            <Card>
              <CardBody className="space-y-3">
                <Skeleton className="h-5 w-1/3" />
                <Skeleton className="h-5 w-1/2" />
                <Skeleton className="h-5 w-1/4" />
              </CardBody>
            </Card>
          ) : accounts.length === 0 ? (
            <EmptyState
              title="No accounts connected"
              description="Connect a platform above to start publishing from this brand."
            />
          ) : (
            <ul className="space-y-3">
              {accounts.map((account) => {
                const expiry = formatExpiry(account.token_expires_at);
                return (
                  <li key={account.id}>
                    <Card>
                      <CardBody className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            <h3 className="text-sm font-semibold text-slate-900">
                              {platformLabel(account.platform)}
                            </h3>
                            <Badge tone={STATUS_TONE[account.status]}>{STATUS_LABEL[account.status]}</Badge>
                          </div>
                          <p className="mt-1 text-sm text-slate-500">
                            {account.external_account_id
                              ? `Account ID: ${account.external_account_id}`
                              : "No account ID on file"}
                          </p>
                          {expiry ? (
                            <p className="mt-0.5 text-sm text-slate-500">
                              {account.status === "expired" ? "Expired" : "Expires"} {expiry}
                            </p>
                          ) : null}
                        </div>
                        <Button variant="danger" size="sm" onClick={() => setPendingDisconnect(account)}>
                          Disconnect
                        </Button>
                      </CardBody>
                    </Card>
                  </li>
                );
              })}
            </ul>
          )}
        </div>
      )}

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
          <p className="text-sm text-slate-600">
            Disconnect {platformLabel(pendingDisconnect.platform)}? Raindeer will no longer be able to
            publish to this account until it&apos;s reconnected.
          </p>
        ) : null}
      </Modal>
    </div>
  );
}
