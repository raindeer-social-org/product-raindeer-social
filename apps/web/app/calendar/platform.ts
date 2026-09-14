// Presentational per-platform identity — a colored left border + a 2-letter
// initial badge on each event card (mirrors the design mockup's calendar
// event chips). Includes platforms beyond
// apps/api/models/content_calendar_event.py::SUPPORTED_PLATFORMS (e.g.
// instagram) so the same map can label a platform on an already-existing
// event even before this app's publishing adapters support scheduling new
// ones there.
export const PLATFORM_COLORS: Record<string, string> = {
  linkedin: "#0A66C2",
  x: "#111111",
  instagram: "#E1306C",
  youtube: "#FF0033",
  facebook: "#1877F2",
};

export const PLATFORM_LABELS: Record<string, string> = {
  linkedin: "LinkedIn",
  x: "X",
  instagram: "Instagram",
  youtube: "YouTube",
  facebook: "Facebook",
};

const DEFAULT_COLOR = "#8B96B2";

/** The color for an event's primary (first) target platform. */
export function primaryPlatformColor(platforms: string[]): string {
  return PLATFORM_COLORS[platforms[0]] ?? DEFAULT_COLOR;
}

export function platformInitial(platform: string): string {
  return (PLATFORM_LABELS[platform] ?? platform).slice(0, 2).toUpperCase();
}

export function platformLabel(platform: string): string {
  return PLATFORM_LABELS[platform] ?? platform;
}
