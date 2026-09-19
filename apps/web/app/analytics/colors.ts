import type { EngagementSnapshotPoint, PlatformAggregate } from "@/lib/api";

// Chart color roles — dataviz skill's validated default categorical palette
// (references/palette.md), copied verbatim: this fixed 8-hue order clears
// the CVD/contrast checks in the skill's validator, so slot assignment
// must stay in this order rather than being generated per chart.
//
// Light-mode only: this app's design system (apps/web/components/ui/) has
// no dark-mode variants anywhere yet, so the chart layer matches it rather
// than introducing a dark theme unilaterally.
export const CATEGORICAL_PALETTE = [
  "#2a78d6", // slot 1 — blue
  "#eb6834", // slot 2 — orange
  "#1baf7a", // slot 3 — aqua
  "#eda100", // slot 4 — yellow
  "#e87ba4", // slot 5 — magenta
  "#008300", // slot 6 — green
  "#4a3aa7", // slot 7 — violet
  "#e34948", // slot 8 — red
] as const;

// A single series (one metric, one bar chart) always uses slot 1 — see
// anti-patterns.md: "one series -> one color (slot 1) for every bar,"
// never a value-ramp over nominal categories like platform names.
export const SINGLE_SERIES_COLOR = CATEGORICAL_PALETTE[0];

// Chart chrome — pinned to this app's "ink" design-system scale
// (apps/web/tailwind.config.ts, sourced from the Raindeer mockup) rather
// than importing a second gray ramp, so charts read as part of the same
// system as every other restyled page. Mirrors the roles in palette.md's
// "Chart chrome & ink" table, mapped onto the nearest ink-* step by
// lightness.
export const CHART_CHROME = {
  gridline: "#E3E8F5", // ink-50 hairline
  axis: "#C7D2EC", // ink-100 baseline
  mutedText: "#98A2BC", // ink-200 axis/tick labels
  secondaryText: "#6A7691", // ink-400
  primaryText: "#0A1633", // ink-950
  surface: "#ffffff",
};

// Platforms known ahead of time get a pinned slot so the same platform is
// always the same color across every chart on the page (color follows the
// entity, never its rank in the current response — anti-patterns.md).
// apps/api/models/content_calendar_event.py::SUPPORTED_PLATFORMS is
// ("linkedin", "x") today; the rest are reserved for platforms this app
// is likely to add next (apps/api/models/social_account.py::SocialPlatform
// currently only defines LINKEDIN, but EngagementSnapshot.platform is a
// free string sourced from Post.publish_results, so future platforms can
// show up in analytics data before they get a dedicated enum member).
const KNOWN_PLATFORM_SLOTS: Record<string, number> = {
  linkedin: 0,
  x: 1,
  twitter: 1, // alias, in case a caller ever sends the old name
  instagram: 2,
  facebook: 3,
  tiktok: 4,
  youtube: 5,
  pinterest: 6,
  threads: 7,
};

/**
 * Stable color for a platform name. Known platforms get a pinned slot;
 * anything else falls back to a slot chosen from its position in
 * `fallbackOrder` (the order platforms first appeared in this response),
 * so an unrecognized platform is still consistent within one page load.
 */
export function colorForPlatform(platform: string, fallbackOrder: string[]): string {
  const key = platform.toLowerCase();
  const knownSlot = KNOWN_PLATFORM_SLOTS[key];
  if (knownSlot !== undefined) {
    return CATEGORICAL_PALETTE[knownSlot];
  }
  const index = fallbackOrder.indexOf(platform);
  const slot = (Object.keys(KNOWN_PLATFORM_SLOTS).length + Math.max(index, 0)) % CATEGORICAL_PALETTE.length;
  return CATEGORICAL_PALETTE[slot];
}

export const METRIC_LABELS = {
  likes: "Likes",
  comments: "Comments",
  shares: "Shares",
  impressions: "Impressions",
} as const;

export type MetricKey = keyof typeof METRIC_LABELS;

export const METRIC_KEYS: MetricKey[] = ["likes", "comments", "shares", "impressions"];

export function metricTotal(aggregate: PlatformAggregate, metric: MetricKey): number {
  switch (metric) {
    case "likes":
      return aggregate.total_likes;
    case "comments":
      return aggregate.total_comments;
    case "shares":
      return aggregate.total_shares;
    case "impressions":
      return aggregate.total_impressions;
  }
}

export function metricAverage(aggregate: PlatformAggregate, metric: MetricKey): number {
  switch (metric) {
    case "likes":
      return aggregate.average_likes;
    case "comments":
      return aggregate.average_comments;
    case "shares":
      return aggregate.average_shares;
    case "impressions":
      return aggregate.average_impressions;
  }
}

export function metricFromSnapshot(point: EngagementSnapshotPoint, metric: MetricKey): number {
  switch (metric) {
    case "likes":
      return point.likes;
    case "comments":
      return point.comments;
    case "shares":
      return point.shares;
    case "impressions":
      return point.impressions;
  }
}
