"use client";

import { useCallback, useEffect, useState, type ReactNode } from "react";
import {
  ApiError,
  connectFacebook,
  connectInstagram,
  connectLinkedIn,
  connectThreads,
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
};

function platformLabel(platform: SocialPlatform): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

function IconLinkedIn() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3" y="3" width="18" height="18" rx="3" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="8" cy="8.5" r="1.3" fill="currentColor" />
      <path d="M8 11.5v6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
      <path
        d="M12.5 17.5v-3.5c0-1.4 1-2.5 2.4-2.5s2.1 1 2.1 2.5v3.5"
        stroke="currentColor"
        strokeWidth="1.8"
        strokeLinecap="round"
      />
      <path d="M12.5 11.5v6" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" />
    </svg>
  );
}

function IconInstagram() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <rect x="3.5" y="3.5" width="17" height="17" rx="5" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="12" cy="12" r="4" stroke="currentColor" strokeWidth="1.8" />
      <circle cx="17" cy="7" r="1" fill="currentColor" />
    </svg>
  );
}

function IconThreads() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M9.5 9.2c1.6-1 4.4-.9 5.1.9.6 1.6-.3 2.7-1.9 3-1.7.3-3.4-.2-3.6-1.6-.2-1.3 1-2 2.3-2 1.6 0 2.9.9 2.9 2.4 0 2-1.7 3.4-4 3.4"
        stroke="currentColor"
        strokeWidth="1.4"
        strokeLinecap="round"
      />
    </svg>
  );
}

function IconFacebook() {
  return (
    <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
      <circle cx="12" cy="12" r="8.5" stroke="currentColor" strokeWidth="1.8" />
      <path
        d="M13.8 9.2h-1.3c-.6 0-1 .5-1 1.1v1.4H13.8l-.3 1.9h-1.9v5.2"
        stroke="currentColor"
        strokeWidth="1.6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

const PLATFORM_ICONS: Partial<Record<SocialPlatform, () => ReactNode>> = {
  linkedin: IconLinkedIn,
  instagram: IconInstagram,
  threads: IconThreads,
  facebook: IconFacebook,
};

// Platforms the UI can start a connect flow for, plus a lookup table (not
// hardcoded per-platform buttons/handlers) so adding one more provider is a
// data change here rather than a rewrite of this page.
const CONNECTABLE_PLATFORMS: SocialPlatform[] = ["linkedin", "instagram", "threads", "facebook"];

const CONNECT_HANDLERS: Partial<
  Record<SocialPlatform, (token: string, brandId: string) => Promise<AuthorizeUrlResponse>>
> = {
  linkedin: connectLinkedIn,
  instagram: connectInstagram,
  threads: connectThreads,
  facebook: connectFacebook,
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
              {CONNECTABLE_PLATFORMS.map((platform) => {
                const Icon = PLATFORM_ICONS[platform];
                return (
                  <div key={platform} className="flex flex-col gap-1.5">
                    <Button
                      variant="primary"
                      isLoading={connectingPlatform === platform}
                      onClick={() => handleConnect(platform)}
                    >
                      <span className="flex items-center gap-2">
                        {Icon ? <Icon /> : null}
                        Connect {platformLabel(platform)}
                      </span>
                    </Button>
                    {notConfiguredPlatform === platform ? (
                      <p role="alert" className="max-w-xs text-sm text-amber-700">
                        {platformLabel(platform)} isn&apos;t configured on this server yet.
                      </p>
                    ) : null}
                  </div>
                );
              })}
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
                const Icon = PLATFORM_ICONS[account.platform];
                return (
                  <li key={account.id}>
                    <Card>
                      <CardBody className="flex flex-wrap items-center justify-between gap-4">
                        <div>
                          <div className="flex items-center gap-2">
                            {Icon ? (
                              <span className="text-slate-500" aria-hidden="true">
                                <Icon />
                              </span>
                            ) : null}
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
