"use client";

import { useMemo, useState } from "react";
import { BLOCK_LIBRARY } from "./block-library";

/** Static visual list of block types (Issue #124 scopes this to
 * read-only — no drag-drop). The search box filters the static list
 * client-side, which is cheap and harmless to include even though
 * dragging blocks onto the canvas is out of scope. */
export function LibraryPanel() {
  const [query, setQuery] = useState("");

  const groups = useMemo(() => {
    const q = query.trim().toLowerCase();
    if (!q) return BLOCK_LIBRARY;
    return BLOCK_LIBRARY.map((group) => ({
      ...group,
      items: group.items.filter((item) => item.label.toLowerCase().includes(q)),
    })).filter((group) => group.items.length > 0);
  }, [query]);

  return (
    <aside className="flex min-h-0 flex-col border-r border-arenadark-border bg-arenadark-panel">
      <div className="border-b border-arenadark-border px-3 pb-2.5 pt-3">
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Search blocks…"
          aria-label="Search blocks"
          className="h-8 w-full rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 px-2.5 text-xs text-arenadark-text2 outline-none placeholder:text-arenadark-muted"
        />
      </div>
      <div className="flex-1 overflow-auto px-2.5 py-2.5">
        {groups.length === 0 ? (
          <p className="px-1 text-xs text-arenadark-muted">No blocks match &ldquo;{query}&rdquo;.</p>
        ) : (
          groups.map((group) => (
            <div key={group.group} className="mb-3.5">
              <div className="mb-1.5 px-0.5 text-[9.5px] font-extrabold tracking-[.13em] text-arenadark-muted">
                {group.group}
              </div>
              <div className="flex flex-col gap-1">
                {group.items.map((item) => (
                  <div
                    key={item.label}
                    className="flex items-center gap-2 rounded-[9px] border border-arenadark-border bg-arenadark-panel3 px-2 py-1.5"
                  >
                    <span
                      className="flex h-[18px] w-[18px] flex-none items-center justify-center rounded-[5px] text-[9.5px] font-extrabold text-white"
                      style={{ background: item.color }}
                    >
                      {item.icon}
                    </span>
                    <span className="text-[11.5px] font-semibold text-arenadark-text2">{item.label}</span>
                  </div>
                ))}
              </div>
            </div>
          ))
        )}
      </div>
    </aside>
  );
}
