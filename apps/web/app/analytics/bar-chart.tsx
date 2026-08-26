"use client";

import { useState } from "react";
import { CHART_CHROME } from "./colors";

export interface BarDatum {
  label: string;
  value: number;
  color: string;
}

// A single-metric comparison across a handful of categories (platforms).
// One series -> one color per bar comes from the caller (anti-patterns.md:
// never a value-ramp over nominal categories), so this component just
// lays out whatever colors it's given.
//
// Mark spec (dataviz skill, marks-and-anatomy.md): bars <= 24px thick with
// a 4px rounded data-end, square at the baseline; hairline recessive
// gridlines; direct value label at the bar's tip when it fits, else the
// tooltip carries it. The plot height below includes the x-axis label
// band so this card never needs a nested scroll.
export function BarChart({
  data,
  formatValue,
  ariaLabel,
}: {
  data: BarDatum[];
  formatValue: (value: number) => string;
  ariaLabel: string;
}) {
  const [hovered, setHovered] = useState<number | null>(null);

  const width = 480;
  const height = 220;
  const paddingLeft = 8;
  const paddingRight = 8;
  const paddingTop = 24;
  const axisBand = 28;
  const plotHeight = height - axisBand - paddingTop;
  const plotWidth = width - paddingLeft - paddingRight;

  const maxValue = Math.max(1, ...data.map((d) => d.value));
  // Round the axis ceiling up to a clean step so gridline ticks read as
  // 0 / round-number / ... rather than an arbitrary max.
  const niceMax = niceCeiling(maxValue);
  const ticks = [0, 0.25, 0.5, 0.75, 1].map((f) => f * niceMax);

  const barSlot = plotWidth / Math.max(data.length, 1);
  const barWidth = Math.min(40, barSlot * 0.5);

  if (data.length === 0) {
    return null;
  }

  return (
    <div role="img" aria-label={ariaLabel} className="w-full">
      <svg viewBox={`0 0 ${width} ${height}`} className="w-full" style={{ maxHeight: 260 }}>
        {/* gridlines */}
        {ticks.map((tick) => {
          const y = paddingTop + plotHeight - (tick / niceMax) * plotHeight;
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
              <text x={0} y={y - 3} fontSize={9} fill={CHART_CHROME.mutedText}>
                {formatValue(tick)}
              </text>
            </g>
          );
        })}

        {data.map((d, i) => {
          const barHeight = (d.value / niceMax) * plotHeight;
          const x = paddingLeft + i * barSlot + (barSlot - barWidth) / 2;
          const y = paddingTop + plotHeight - barHeight;
          const isHovered = hovered === i;
          const labelFits = barHeight > 14;
          return (
            <g
              key={d.label}
              onMouseEnter={() => setHovered(i)}
              onMouseLeave={() => setHovered((current) => (current === i ? null : current))}
              onFocus={() => setHovered(i)}
              onBlur={() => setHovered((current) => (current === i ? null : current))}
              tabIndex={0}
              role="graphics-symbol"
              aria-label={`${d.label}: ${formatValue(d.value)}`}
              style={{ cursor: "pointer", outline: "none" }}
            >
              {/* transparent full-height hit target, bigger than the bar */}
              <rect
                x={paddingLeft + i * barSlot}
                y={paddingTop}
                width={barSlot}
                height={plotHeight}
                fill="transparent"
              />
              <rect
                x={x}
                y={y}
                width={barWidth}
                height={Math.max(barHeight, 1)}
                rx={4}
                fill={d.color}
                opacity={isHovered ? 0.85 : 1}
              />
              {labelFits ? (
                <text
                  x={x + barWidth / 2}
                  y={y - 5}
                  fontSize={10}
                  textAnchor="middle"
                  fill={CHART_CHROME.secondaryText}
                >
                  {formatValue(d.value)}
                </text>
              ) : null}
              <text
                x={x + barWidth / 2}
                y={height - axisBand + 16}
                fontSize={10}
                textAnchor="middle"
                fill={CHART_CHROME.secondaryText}
              >
                {d.label}
              </text>
              {isHovered ? (
                <g transform={`translate(${x + barWidth / 2}, ${y - 22})`}>
                  <rect
                    x={-34}
                    y={-16}
                    width={68}
                    height={20}
                    rx={4}
                    fill={CHART_CHROME.primaryText}
                    opacity={0.9}
                  />
                  <text x={0} y={-2} fontSize={10} textAnchor="middle" fill="#ffffff">
                    {formatValue(d.value)}
                  </text>
                </g>
              ) : null}
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
      </svg>
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
