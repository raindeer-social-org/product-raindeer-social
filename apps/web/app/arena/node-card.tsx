"use client";

import type { ArenaNodeView } from "./build-nodes";
import { STATUS_STYLES } from "./status-styles";

export function NodeCard({
  node,
  isSelected,
  onSelect,
}: {
  node: ArenaNodeView;
  isSelected: boolean;
  onSelect: (id: string) => void;
}) {
  const statusStyle = STATUS_STYLES[node.status];
  const isLive = node.status === "WAITING";

  return (
    <button
      type="button"
      onClick={() => onSelect(node.id)}
      aria-pressed={isSelected}
      aria-label={`Select ${node.name}`}
      style={{
        left: node.x,
        top: node.y,
        width: node.w,
        borderColor: isSelected ? "#3D6BFF" : node.status === "WAITING" ? "#7A5A1E" : "#1D2743",
        boxShadow: isSelected
          ? "0 0 0 3px rgba(61,107,255,.18)"
          : isLive
            ? "0 0 26px -8px rgba(43,109,255,.7)"
            : "none",
      }}
      className="absolute flex cursor-pointer flex-col overflow-hidden rounded-[13px] border-[1.5px] bg-arenadark-panel2 text-left"
    >
      <div
        className="flex items-center gap-1.5 border-b border-arenadark-border px-2.5 py-2"
        style={{ background: isSelected ? "#17224A" : "#0F1731" }}
      >
        <div
          className="flex h-[19px] w-[19px] flex-none items-center justify-center rounded-[6px] text-[9px] font-extrabold text-white"
          style={{ background: node.color }}
        >
          {node.initial}
        </div>
        <span className="min-w-0 flex-1 truncate text-[11.5px] font-bold text-arenadark-text">{node.name}</span>
        <span
          className="flex-none rounded-[5px] px-[5px] py-[2px] text-[8.5px] font-extrabold tracking-wide"
          style={{ color: statusStyle.fg, background: statusStyle.bg }}
        >
          {statusStyle.label}
        </span>
      </div>
      <div className="flex flex-col gap-1 px-2.5 py-2">
        {node.lines.map((line, i) => (
          <div key={i} className="truncate font-mono text-[10.5px] leading-tight text-arenadark-text3">
            {line}
          </div>
        ))}
      </div>
      <div className="mt-auto truncate border-t border-[#161F3C] bg-arenadark-panel px-2.5 py-1.5 font-mono text-[9.5px] text-arenadark-muted">
        {node.footer}
      </div>
    </button>
  );
}
