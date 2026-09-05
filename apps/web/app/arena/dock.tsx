"use client";

import { useState } from "react";
import type { ArenaRun } from "@/lib/api";
import { buildCostRows, buildDraftThumbs, buildSources, buildTrace, totalCost, totalTokens } from "./build-dock";
import { formatClock, formatCost, formatTokens } from "./format";

type DockTab = "trace" | "outputs" | "cost" | "sources";

const AGENT_COLOR: Record<string, string> = {
  Ved: "#8FB4FF",
  Keshav: "#C9A6FF",
  Kavi: "#6BE3B0",
  Neer: "#FFC46B",
  system: "#7C8AB4",
  Scheduler: "#7FD4FF",
  Publisher: "#7FD4FF",
  Analytics: "#FF9BC4",
};

export function Dock({ run }: { run: ArenaRun }) {
  const [tab, setTab] = useState<DockTab>("trace");
  const trace = buildTrace(run);
  const costRows = buildCostRows(run);
  const sources = buildSources(run);
  const drafts = buildDraftThumbs(run);

  const tabs: { id: DockTab; label: string; count: number | string }[] = [
    { id: "trace", label: "Trace", count: trace.length },
    { id: "outputs", label: "Outputs", count: Object.keys(run.post?.body_text ?? {}).length },
    { id: "cost", label: "Cost", count: formatCost(totalCost(run)) },
    { id: "sources", label: "Sources", count: sources.length },
  ];

  return (
    <div className="grid h-[196px] min-h-0 grid-cols-[minmax(0,1fr)_320px] border-t border-arenadark-border bg-arenadark-panel">
      <div className="flex min-h-0 flex-col border-r border-arenadark-border">
        <div className="flex items-center gap-1 px-3.5 pt-2">
          {tabs.map((t) => (
            <button
              key={t.id}
              type="button"
              onClick={() => setTab(t.id)}
              aria-pressed={tab === t.id}
              className="rounded-t-lg px-2.5 py-1.5 text-[11.5px] font-bold"
              style={{ color: tab === t.id ? "#fff" : "#7C8AB4", background: tab === t.id ? "#131C3B" : "transparent" }}
            >
              {t.label} <span className="font-semibold text-arenadark-muted">{t.count}</span>
            </button>
          ))}
        </div>

        <div className="flex-1 overflow-auto px-3.5 py-2">
          {tab === "trace" &&
            (trace.length === 0 ? (
              <EmptyDockState text="No agent runs logged yet for this run." />
            ) : (
              <ul className="flex flex-col gap-1.5" aria-label="Run trace">
                {[...trace].reverse().map((entry) => (
                  <li key={entry.id} className="flex items-start gap-2.5">
                    <span className="flex-none pt-px font-mono text-[10px] text-arenadark-muted">
                      {formatClock(entry.time)}
                    </span>
                    <span
                      className="w-[70px] flex-none text-[10.5px] font-extrabold"
                      style={{ color: AGENT_COLOR[entry.who] ?? "#93A2CC" }}
                    >
                      {entry.who}
                    </span>
                    <span className="min-w-0 text-[11.5px] leading-relaxed text-arenadark-text3">{entry.text}</span>
                  </li>
                ))}
              </ul>
            ))}

          {tab === "outputs" &&
            (!run.post?.body_text || Object.keys(run.post.body_text).length === 0 ? (
              <EmptyDockState text="No generated copy yet — Generation hasn't run." />
            ) : (
              <ul className="flex flex-col gap-2">
                {Object.entries(run.post.body_text).map(([platform, text]) => (
                  <li key={platform} className="rounded-[9px] border border-arenadark-border3 bg-arenadark-panel3 px-2.5 py-2">
                    <div className="mb-1 text-[9.5px] font-extrabold uppercase tracking-wide text-arenadark-muted">
                      {platform}
                    </div>
                    <p className="text-[11.5px] leading-relaxed text-arenadark-text2">{text}</p>
                  </li>
                ))}
              </ul>
            ))}

          {tab === "cost" &&
            (costRows.length === 0 ? (
              <EmptyDockState text="No cost/token data recorded yet." />
            ) : (
              <div>
                <div className="mb-2 flex gap-4 text-[11.5px] text-arenadark-text2">
                  <span>
                    Total cost <b className="text-white">{formatCost(totalCost(run))}</b>
                  </span>
                  <span>
                    Total tokens <b className="text-white">{formatTokens(totalTokens(run))}</b>
                  </span>
                </div>
                <ul className="flex flex-col gap-1">
                  {costRows.map((row) => (
                    <li key={row.agentType} className="flex items-center gap-3 text-[11.5px] text-arenadark-text3">
                      <span className="w-20 flex-none font-bold" style={{ color: AGENT_COLOR[row.who] ?? "#93A2CC" }}>
                        {row.who}
                      </span>
                      <span className="w-28 flex-none font-mono text-[10.5px]">{row.model}</span>
                      <span className="w-16 flex-none">{row.tokens} tok</span>
                      <span>{row.cost}</span>
                    </li>
                  ))}
                </ul>
              </div>
            ))}

          {tab === "sources" &&
            (sources.length === 0 ? (
              <EmptyDockState text="No sources yet — Research hasn't run." />
            ) : (
              <ul className="flex flex-col gap-1.5">
                {sources.map((source) => (
                  <li key={source.url} className="text-[11.5px]">
                    <a
                      href={source.url}
                      target="_blank"
                      rel="noreferrer"
                      className="font-semibold text-arenadark-text2 hover:underline"
                    >
                      {source.title}
                    </a>
                    <span className="ml-2 text-[11px] text-arenadark-muted">{source.domain}</span>
                  </li>
                ))}
              </ul>
            ))}
        </div>
      </div>

      <div className="flex min-h-0 flex-col">
        <div className="flex items-center gap-2 px-3.5 pb-1.5 pt-2.5">
          <span className="text-[9.5px] font-extrabold tracking-[.13em] text-arenadark-muted">DRAFT MEDIA</span>
          <span className="rounded-[5px] bg-[#152249] px-1.5 py-0.5 text-[10px] font-bold text-[#8FB4FF]">
            {drafts.length}
          </span>
        </div>
        <div className="flex flex-1 gap-2 overflow-auto px-3.5 pb-3">
          {drafts.length === 0 ? (
            <EmptyDockState text="No media generated for this run yet." />
          ) : (
            drafts.map((draft, i) => (
              <div key={i} className="w-28 flex-none overflow-hidden rounded-[10px] border border-arenadark-border3 bg-arenadark-panel3">
                {/* eslint-disable-next-line @next/next/no-img-element -- real Post.media URLs from arbitrary storage hosts, same as components/ui/Avatar.tsx */}
                <img src={draft.url} alt={`${draft.platform} draft`} className="h-[78px] w-full object-cover" />
                <div className="flex items-center gap-1 px-2 py-1.5">
                  <span className="rounded-[4px] bg-arenadark-border3 px-1 text-[8.5px] font-extrabold text-white">
                    {draft.platform}
                  </span>
                  <span className="truncate text-[9.5px] text-arenadark-muted2">{draft.format}</span>
                </div>
              </div>
            ))
          )}
        </div>
      </div>
    </div>
  );
}

function EmptyDockState({ text }: { text: string }) {
  return <p className="text-[11.5px] italic text-arenadark-muted">{text}</p>;
}
