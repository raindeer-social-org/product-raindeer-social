"use client";

import type { ArenaNodeView } from "./build-nodes";

const isStageNode = (node: ArenaNodeView) => node.id !== "brief" && node.id !== "brand";

export function Inspector({ node }: { node: ArenaNodeView }) {
  return (
    <aside className="flex min-h-0 flex-col border-l border-arenadark-border bg-arenadark-panel">
      <div className="border-b border-arenadark-border px-4 py-3.5">
        <div className="mb-2.5 flex items-center gap-2.5">
          <div
            className="flex h-[26px] w-[26px] flex-none items-center justify-center rounded-lg text-[11px] font-extrabold text-white"
            style={{ background: node.color }}
          >
            {node.initial}
          </div>
          <div className="min-w-0 flex-1">
            <div className="truncate text-sm font-bold text-white">{node.name}</div>
            <div className="truncate text-[10.5px] text-arenadark-muted2">{node.sub}</div>
          </div>
        </div>
        <div className="grid grid-cols-3 gap-1.5">
          {node.stats.length > 0 ? (
            node.stats.map((stat) => (
              <div key={stat.label} className="rounded-[9px] border border-arenadark-border bg-arenadark-panel3 px-2 py-1.5">
                <div className="text-[9px] font-bold tracking-wide text-arenadark-muted">{stat.label}</div>
                <div className="mt-0.5 text-[12.5px] font-extrabold text-arenadark-text2">{stat.value}</div>
              </div>
            ))
          ) : (
            <div className="col-span-3 text-[11px] text-arenadark-muted">No stats yet</div>
          )}
        </div>
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-3 overflow-auto px-4 py-3.5">
        <div>
          <div className="mb-1.5 text-[10.5px] font-bold text-arenadark-muted2">Summary</div>
          <div className="flex flex-col gap-1 rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 px-2.5 py-2">
            {node.lines.map((line, i) => (
              <div key={i} className="font-mono text-[11.5px] leading-relaxed text-arenadark-text2">
                {line}
              </div>
            ))}
          </div>
        </div>

        {isStageNode(node) && (
          <div>
            <div className="mb-1.5 text-[10.5px] font-bold text-arenadark-muted2">System prompt · editable</div>
            <div className="rounded-[9px] border border-dashed border-arenadark-border3 bg-arenadark-panel3 px-2.5 py-2.5 text-[11.5px] italic text-arenadark-muted">
              Not available yet — this stage&apos;s AgentRun only records{" "}
              <code className="not-italic">{"{post_id}"}</code> as input, not the prompt actually sent.
            </div>
          </div>
        )}

        {isStageNode(node) && (
          <div className="min-h-0">
            <div className="mb-1.5 text-[10.5px] font-bold text-arenadark-muted2">Raw output</div>
            {node.agentRun?.output ? (
              <pre className="max-h-40 overflow-auto whitespace-pre-wrap break-words rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 px-2.5 py-2 font-mono text-[10.5px] leading-relaxed text-arenadark-text3">
                {JSON.stringify(node.agentRun.output, null, 2)}
              </pre>
            ) : (
              <div className="rounded-[9px] border border-dashed border-arenadark-border3 bg-arenadark-panel3 px-2.5 py-2.5 text-[11.5px] italic text-arenadark-muted">
                No output recorded yet — this stage hasn&apos;t run.
              </div>
            )}
          </div>
        )}
      </div>

      <div className="flex flex-col gap-1.5 border-t border-arenadark-border px-4 py-3">
        <button
          type="button"
          disabled
          title="Coming soon"
          className="h-9 cursor-not-allowed rounded-[10px] bg-brand-600/30 text-[12.5px] font-bold text-white/50"
        >
          Re-run from this block · Coming soon
        </button>
        <div className="flex gap-1.5">
          {["Add branch", "Pin output", "Mute"].map((label) => (
            <button
              key={label}
              type="button"
              disabled
              title="Coming soon"
              className="h-8 flex-1 cursor-not-allowed rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 text-[11.5px] font-semibold text-arenadark-muted2"
            >
              {label}
            </button>
          ))}
        </div>
      </div>
    </aside>
  );
}
