// Static block-type palette for the left sidebar (Issue #124 scopes this
// to "a static visual list of block types — no drag-drop needed"). This
// is UI chrome describing what kinds of blocks the pipeline is built
// from, not per-run telemetry, so it's fine for it to be a fixed list
// rather than derived from a specific run.
export interface LibraryItem {
  icon: string;
  label: string;
  color: string;
}

export interface LibraryGroup {
  group: string;
  items: LibraryItem[];
}

export const BLOCK_LIBRARY: LibraryGroup[] = [
  {
    group: "AGENTS",
    items: [
      { icon: "V", label: "Research · Ved", color: "#1B4DFF" },
      { icon: "K", label: "Creative · Keshav", color: "#6B32C9" },
      { icon: "K", label: "Generation · Kavi", color: "#0E7A4E" },
      { icon: "N", label: "Reviewer · Neer", color: "#B46A00" },
      { icon: "A", label: "Onboarding · Aarav", color: "#2C5FD6" },
    ],
  },
  {
    group: "TOOLS",
    items: [
      { icon: "⌕", label: "Web search", color: "#2B3D6B" },
      { icon: "↗", label: "Trend radar", color: "#2B3D6B" },
      { icon: "▧", label: "Image gen", color: "#2B3D6B" },
      { icon: "▶", label: "Video gen", color: "#2B3D6B" },
    ],
  },
  {
    group: "DATA",
    items: [
      { icon: "B", label: "Brand memory", color: "#0B2A6B" },
      { icon: "◍", label: "Audience", color: "#0B2A6B" },
      { icon: "▲", label: "Past performance", color: "#0B2A6B" },
    ],
  },
  {
    group: "FLOW",
    items: [
      { icon: "☺", label: "Human approval", color: "#1B4DFF" },
      { icon: "◇", label: "Condition", color: "#8B5BD6" },
      { icon: "◷", label: "Wait until", color: "#8B5BD6" },
    ],
  },
  {
    group: "OUTPUT",
    items: [
      { icon: "◷", label: "Scheduler", color: "#1E7FB8" },
      { icon: "➤", label: "Publisher", color: "#1E7FB8" },
      { icon: "▲", label: "Analytics loop", color: "#C2477F" },
    ],
  },
];
