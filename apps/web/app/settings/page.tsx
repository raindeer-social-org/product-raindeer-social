"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import {
  ApiError,
  fetchBrandSettings,
  fetchSocialAccounts,
  updateBrandSettings,
  type BrandSettings,
  type BrandSettingsUpdateInput,
  type SocialAccount,
  type SocialAccountStatus,
  type SocialPlatform,
} from "@/lib/api";
import { useAuth } from "@/lib/auth-context";
import { useBrand } from "@/lib/brand-context";
import { Badge, type BadgeTone } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { Switch } from "@/components/ui/Switch";
import { useToast } from "@/components/ui/Toast";

// Same label lookup as apps/web/app/social-accounts/page.tsx — kept in
// sync there rather than imported, since that file doesn't export it.
const PLATFORM_LABELS: Partial<Record<SocialPlatform, string>> = {
  linkedin: "LinkedIn",
};

function platformLabel(platform: SocialPlatform): string {
  return PLATFORM_LABELS[platform] ?? platform;
}

const STATUS_TONE: Record<SocialAccountStatus, BadgeTone> = {
  active: "green",
  expired: "amber",
  revoked: "slate",
};

const STATUS_LABEL: Record<SocialAccountStatus, string> = {
  active: "Connected",
  expired: "Expired",
  revoked: "Not connected",
};

type ToggleKey =
  | "auto_approve_enabled"
  | "show_agent_reasoning"
  | "email_review_digest_enabled"
  | "auto_shift_posting_times";

const TOGGLES: { key: ToggleKey; label: string; sub: string }[] = [
  {
    key: "auto_approve_enabled",
    label: "Auto-approve posts above the score threshold",
    sub: "Everything else waits for you in the Review Queue",
  },
  {
    key: "show_agent_reasoning",
    label: "Show agent reasoning in the Arena",
    sub: "Full tool calls and intermediate output",
  },
  {
    key: "email_review_digest_enabled",
    label: "Email me when a post needs review",
    sub: "Daily digest",
  },
  {
    key: "auto_shift_posting_times",
    label: "Let Ved shift posting times automatically",
    sub: "Based on engagement data from Analytics",
  },
];

function ChannelsCardBody({ accounts }: { accounts: SocialAccount[] }) {
  if (accounts.length === 0) {
    return (
      <EmptyState
        title="No channels connected"
        description="Connect a platform from the Connections page to start publishing."
      />
    );
  }

  return (
    <ul className="grid grid-cols-1 gap-3 sm:grid-cols-2">
      {accounts.map((account) => (
        <li
          key={account.id}
          className="flex items-center justify-between gap-3 rounded-[13px] border border-line-soft px-3.5 py-3"
        >
          <div className="min-w-0">
            <div className="text-[13.5px] font-bold text-ink-950">{platformLabel(account.platform)}</div>
            <div className="mt-0.5 text-[11.5px] text-ink-300">
              {account.external_account_id ?? "Connected account"}
            </div>
          </div>
          <Badge tone={STATUS_TONE[account.status]}>{STATUS_LABEL[account.status]}</Badge>
        </li>
      ))}
    </ul>
  );
}

export default function SettingsPage() {
  const { token } = useAuth();
  const { selectedBrand, selectedBrandId } = useBrand();
  const { push } = useToast();

  const [accounts, setAccounts] = useState<SocialAccount[]>([]);
  const [isLoadingAccounts, setIsLoadingAccounts] = useState(false);
  const [accountsError, setAccountsError] = useState<string | null>(null);

  const [settings, setSettings] = useState<BrandSettings | null>(null);
  const [isLoadingSettings, setIsLoadingSettings] = useState(false);
  const [settingsError, setSettingsError] = useState<string | null>(null);
  const [savingKey, setSavingKey] = useState<ToggleKey | "threshold" | null>(null);
  const [thresholdInput, setThresholdInput] = useState("90");

  const loadAccounts = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setAccounts([]);
      return;
    }
    setIsLoadingAccounts(true);
    setAccountsError(null);
    try {
      const result = await fetchSocialAccounts(token, selectedBrandId);
      setAccounts(result);
    } catch (err) {
      setAccountsError(err instanceof Error ? err.message : "Failed to load connected channels");
    } finally {
      setIsLoadingAccounts(false);
    }
  }, [token, selectedBrandId]);

  const loadSettings = useCallback(async () => {
    if (!token || !selectedBrandId) {
      setSettings(null);
      return;
    }
    setIsLoadingSettings(true);
    setSettingsError(null);
    try {
      const result = await fetchBrandSettings(token, selectedBrandId);
      setSettings(result);
      setThresholdInput(String(result.auto_approve_threshold));
    } catch (err) {
      setSettingsError(err instanceof ApiError ? err.message : "Failed to load agent behaviour settings");
    } finally {
      setIsLoadingSettings(false);
    }
  }, [token, selectedBrandId]);

  useEffect(() => {
    setAccounts([]);
    setSettings(null);
    loadAccounts();
    loadSettings();
  }, [loadAccounts, loadSettings]);

  async function persist(patch: BrandSettingsUpdateInput, key: ToggleKey | "threshold") {
    if (!token || !selectedBrandId || !settings) return;
    const previous = settings;
    setSettings({ ...settings, ...patch });
    setSavingKey(key);
    try {
      const result = await updateBrandSettings(token, selectedBrandId, patch);
      setSettings(result);
      setThresholdInput(String(result.auto_approve_threshold));
    } catch (err) {
      setSettings(previous);
      setThresholdInput(String(previous.auto_approve_threshold));
      push(err instanceof ApiError ? err.message : "Failed to save this setting", "error");
    } finally {
      setSavingKey(null);
    }
  }

  function handleToggle(key: ToggleKey, next: boolean) {
    persist({ [key]: next }, key);
  }

  function handleThresholdBlur() {
    if (!settings) return;
    const parsed = Number(thresholdInput);
    if (!Number.isFinite(parsed) || parsed < 0 || parsed > 100) {
      setThresholdInput(String(settings.auto_approve_threshold));
      return;
    }
    if (parsed === settings.auto_approve_threshold) return;
    persist({ auto_approve_threshold: Math.round(parsed) }, "threshold");
  }

  if (!selectedBrand) {
    return (
      <div>
        <PageHeader title="Settings" description="Channels, agents and access." />
        <EmptyState title="No brand selected" description="Choose a brand to see its settings." />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <PageHeader
        title="Settings"
        description={
          <>
            Channels, agents and access for <strong className="text-ink-700">{selectedBrand.name}</strong>.
          </>
        }
      />

      <Card>
        <CardHeader
          title="Connected channels"
          description="Reuses the same connections tracked on the Connections page."
          action={
            <Link href="/social-accounts">
              <Button variant="outline" size="sm">
                Manage connections
              </Button>
            </Link>
          }
        />
        <CardBody>
          {accountsError ? (
            <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
              {accountsError}
            </p>
          ) : isLoadingAccounts && accounts.length === 0 ? (
            <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <Skeleton className="h-16 w-full" />
              <Skeleton className="h-16 w-full" />
            </div>
          ) : (
            <ChannelsCardBody accounts={accounts} />
          )}
        </CardBody>
      </Card>

      <Card>
        <CardHeader
          title="Agent behaviour"
          description="Saved per brand and applied as each capability is wired up — see the note on the auto-shift toggle below."
        />
        <CardBody>
          {settingsError ? (
            <p role="alert" className="rounded-lg bg-danger-bg px-3 py-2 text-sm font-medium text-danger">
              {settingsError}
            </p>
          ) : isLoadingSettings && !settings ? (
            <div className="space-y-3">
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
              <Skeleton className="h-14 w-full" />
            </div>
          ) : settings ? (
            <div className="flex flex-col">
              {TOGGLES.map((toggle, index) => (
                <div key={toggle.key}>
                  <div className="flex items-center gap-3.5 py-3">
                    <div className="flex-1">
                      <div className="text-[13.5px] font-semibold text-ink-950">{toggle.label}</div>
                      <div className="mt-0.5 text-xs text-ink-300">{toggle.sub}</div>
                    </div>
                    <Switch
                      checked={settings[toggle.key]}
                      onChange={(next) => handleToggle(toggle.key, next)}
                      disabled={savingKey === toggle.key}
                      label={toggle.label}
                    />
                  </div>

                  {toggle.key === "auto_approve_enabled" && settings.auto_approve_enabled ? (
                    <div className="mb-3 ml-0.5 flex items-center gap-2 rounded-[11px] bg-canvas px-3 py-2.5">
                      <label htmlFor="auto-approve-threshold" className="text-xs font-medium text-ink-500">
                        Score threshold
                      </label>
                      <input
                        id="auto-approve-threshold"
                        type="number"
                        min={0}
                        max={100}
                        value={thresholdInput}
                        onChange={(event) => setThresholdInput(event.target.value)}
                        onBlur={handleThresholdBlur}
                        disabled={savingKey === "threshold"}
                        className="w-20 rounded-[8px] border border-line bg-white px-2 py-1 text-sm text-ink-950 focus:border-brand-500 focus:outline-none focus:ring-2 focus:ring-brand-500/20"
                      />
                      <span className="text-xs text-ink-300">out of 100</span>
                    </div>
                  ) : null}

                  {toggle.key === "auto_shift_posting_times" ? (
                    <p className="mb-1 text-xs text-ink-300">
                      Note: this preference is saved and will persist across reloads, but the scheduling
                      suggestion service doesn&apos;t consult it automatically yet — that&apos;s a follow-up.
                    </p>
                  ) : null}

                  {index < TOGGLES.length - 1 ? <div className="border-b border-line-faint" /> : null}
                </div>
              ))}
            </div>
          ) : null}
        </CardBody>
      </Card>
    </div>
  );
}
