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
import { PageHeader } from "@/components/ui/PageHeader";
import { Card, CardBody, CardHeader } from "@/components/ui/Card";
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
import { SocialConnectionsPanel } from "./social-connections-panel";

export default function SocialAccountsPage() {
  const { selectedBrand } = useBrand();

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
        <Card>
          <CardHeader
            title="Where you publish"
            description="Connect a platform below — the OAuth flow opens in this tab and brings you back here once it's authorized. Add, remove or re-authorize any of these any time."
          />
          <CardBody>
            <SocialConnectionsPanel />
          </CardBody>
        </Card>
      )}
    </div>
  );
}
