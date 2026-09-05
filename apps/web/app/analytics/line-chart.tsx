"use client";

import type { PointerEvent as ReactPointerEvent } from "react";
import { useMemo, useRef, useState } from "react";
import { CHART_CHROME } from "./colors";

export interface LineSeries {
  name: string;
  color: string;
  points: { t: number; value: number }[]; // t = epoch ms
}

// A real time-series chart (per the issue: "Render the trend as a real
// line/time-series chart per metric"). Mark spec (marks-and-anatomy.md):
// 2px lines, >=8px end markers with a 2px surface ring, a crosshair that
// snaps to the nearest x, one tooltip listing every series at that x, and
// a legend whenever there are 2+ series (color follows the platform
// entity, assigned by the caller so it stays consistent with the bar
// chart/table above).
export function LineChart({
  series,
  formatValue,
  formatTime,
  ariaLabel,
}: {
  series: LineSeries[];
  formatValue: (value: number) => string;
  formatTime: (t: number) => string;
  ariaLabel: string;
}) {
  const svgRef = useRef<SVGSVGElement | null>(null);
  const [hoverX, setHoverX] = useState<number | null>(null);

  const width = 560;
  const height = 220;
  const paddingLeft = 42;
  const paddingRight = 56;
  const paddingTop = 16;
  const axisBand = 24;
  const plotHeight = height - axisBand - paddingTop;
  const plotWidth = width - paddingLeft - paddingRight;

  const allPoints = series.flatMap((s) => s.points);
  const hasData = allPoints.length > 0;

  const minT = hasData ? Math.min(...allPoints.map((p) => p.t)) : 0;
  const maxT = hasData ? Math.max(...allPoints.map((p) => p.t)) : 1;
  const maxValue = hasData ? Math.max(...allPoints.map((p) => p.value)) : 1;
  const niceMax = niceCeiling(Math.max(maxValue, 1));
  const tSpan = Math.max(maxT - minT, 1);

  const xFor = (t: number) => paddingLeft + ((t - minT) / tSpan) * plotWidth;
  const yFor = (value: number) => paddingTop + plotHeight - (value / niceMax) * plotHeight;

  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * niceMax);

  const nearestBySeries = useMemo(() => {
    if (hoverX === null) return null;
    const hoveredT = minT + ((hoverX - paddingLeft) / plotWidth) * tSpan;
    return series.map((s) => {
      if (s.points.length === 0) return null;
      let closest = s.points[0];
      let bestDiff = Math.abs(closest.t - hoveredT);
      for (const p of s.points) {
        const diff = Math.abs(p.t - hoveredT);
        if (diff < bestDiff) {
          closest = p;
          bestDiff = diff;
        }
      }
      return closest;
    });
  }, [hoverX, series, minT, tSpan, plotWidth]);

  function handleMove(event: ReactPointerEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const rect = svg.getBoundingClientRect();
    const scaleX = width / rect.width;
    const localX = (event.clientX - rect.left) * scaleX;
    setHoverX(Math.min(Math.max(localX, paddingLeft), width - paddingRight));
  }

  if (!hasData) {
    return null;
  }

  return (
    <div>
      {series.length >= 2 ? (
        <div className="mb-2 flex flex-wrap gap-x-4 gap-y-1">
          {series.map((s) => (
            <div key={s.name} className="flex items-center gap-1.5 text-xs text-ink-600">
              <span aria-hidden="true" className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: s.color }} />
              {s.name}
            </div>
          ))}
        </div>
      ) : null}
      <div role="img" aria-label={ariaLabel} className="w-full">
        <svg
          ref={svgRef}
          viewBox={`0 0 ${width} ${height}`}
          className="w-full"
          style={{ maxHeight: 260 }}
          onPointerMove={handleMove}
          onPointerLeave={() => setHoverX(null)}
        >
          {ticks.map((tick) => {
            const y = yFor(tick);
            return (
              <g key={tick}>
                <line
                  x1={paddingLeft}
                  x2={width - paddingRight}
                  y1={y}
                  y2={y}
                  stroke={CHART_CHROME.gridline}
                  strokeWidth={1}
                />
                <text x={0} y={y + 3} fontSize={9} fill={CHART_CHROME.mutedText}>
                  {formatValue(tick)}
                </text>
              </g>
            );
          })}

          <line
            x1={paddingLeft}
            x2={width - paddingRight}
            y1={paddingTop + plotHeight}
            y2={paddingTop + plotHeight}
            stroke={CHART_CHROME.axis}
            strokeWidth={1}
          />
          <text x={paddingLeft} y={height - 4} fontSize={9} fill={CHART_CHROME.mutedText}>
            {formatTime(minT)}
          </text>
          <text x={width - paddingRight} y={height - 4} fontSize={9} textAnchor="end" fill={CHART_CHROME.mutedText}>
            {formatTime(maxT)}
          </text>

          {series.map((s) => {
            if (s.points.length === 0) return null;
            const sorted = [...s.points].sort((a, b) => a.t - b.t);
            const d = sorted
              .map((p, i) => `${i === 0 ? "M" : "L"} ${xFor(p.t)} ${yFor(p.value)}`)
              .join(" ");
            const last = sorted[sorted.length - 1];
            return (
              <g key={s.name}>
                <path d={d} fill="none" stroke={s.color} strokeWidth={2} strokeLinejoin="round" strokeLinecap="round" />
                {sorted.map((p) => (
                  <circle
                    key={p.t}
                    cx={xFor(p.t)}
                    cy={yFor(p.value)}
                    r={4}
                    fill={s.color}
                    stroke={CHART_CHROME.surface}
                    strokeWidth={2}
                  />
                ))}
                <text
                  x={xFor(last.t) + 6}
                  y={yFor(last.value) + 3}
                  fontSize={10}
                  fill={CHART_CHROME.secondaryText}
                >
                  {formatValue(last.value)}
                </text>
              </g>
            );
          })}

          {hoverX !== null ? (
            <line
              x1={hoverX}
              x2={hoverX}
              y1={paddingTop}
              y2={paddingTop + plotHeight}
              stroke={CHART_CHROME.axis}
              strokeWidth={1}
            />
          ) : null}
        </svg>
      </div>
      {hoverX !== null && nearestBySeries ? (
        <div className="mt-2 rounded-lg border border-line-soft bg-white p-2 text-xs shadow-card">
          {series.map((s, i) => {
            const point = nearestBySeries[i];
            if (!point) return null;
            return (
              <div key={s.name} className="flex items-center justify-between gap-4 py-0.5">
                <span className="flex items-center gap-1.5 text-ink-400">
                  <span aria-hidden="true" className="inline-block h-0.5 w-3 rounded" style={{ backgroundColor: s.color }} />
                  {s.name}
                  <span className="text-ink-300">{formatTime(point.t)}</span>
                </span>
                <span className="font-semibold text-ink-950">{formatValue(point.value)}</span>
              </div>
            );
          })}
        </div>
      ) : null}
    </div>
  );
}

function niceCeiling(value: number): number {
  if (value <= 0) return 1;
  const magnitude = Math.pow(10, Math.floor(Math.log10(value)));
  const normalized = value / magnitude;
  let niceNormalized: number;
  if (normalized <= 1) niceNormalized = 1;
  else if (normalized <= 2) niceNormalized = 2;
  else if (normalized <= 5) niceNormalized = 5;
  else niceNormalized = 10;
  return niceNormalized * magnitude;
}
