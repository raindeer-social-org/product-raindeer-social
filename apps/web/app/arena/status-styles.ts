import type { NodeStatus } from "./build-nodes";

export const STATUS_STYLES: Record<NodeStatus, { fg: string; bg: string; label: string }> = {
  DONE: { fg: "#8FB4FF", bg: "rgba(143,180,255,.14)", label: "DONE" },
  WAITING: { fg: "#FFC46B", bg: "rgba(255,196,107,.14)", label: "WAITING" },
  QUEUED: { fg: "#7C8AB4", bg: "rgba(124,138,180,.14)", label: "QUEUED" },
  SKIPPED: { fg: "#5B6A96", bg: "rgba(91,106,150,.14)", label: "SKIPPED" },
  READ: { fg: "#8FB4FF", bg: "rgba(143,180,255,.14)", label: "READ" },
};
