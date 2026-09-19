import type { PlatformAggregate } from "@/lib/api";
import { formatAverage, formatCompactNumber } from "./format";

// The accessible, WCAG-clean twin of the bar chart above it (dataviz
// skill, anti-patterns.md: "No table view / color-only encoding on a
// continuous scale" is a failure mode) — every number the chart can show
// is reachable here too, plus the averages the single-metric chart
// doesn't have room for.
export function PlatformTable({ platforms }: { platforms: PlatformAggregate[] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-line-soft text-xs uppercase tracking-wide text-ink-300">
            <th scope="col" className="py-2 pr-4 font-medium">
              Platform
            </th>
            <th scope="col" className="py-2 pr-4 font-medium">
              Snapshots
            </th>
            <th scope="col" className="py-2 pr-4 font-medium">
              Likes
            </th>
            <th scope="col" className="py-2 pr-4 font-medium">
              Comments
            </th>
            <th scope="col" className="py-2 pr-4 font-medium">
              Shares
            </th>
            <th scope="col" className="py-2 font-medium">
              Impressions
            </th>
          </tr>
        </thead>
        <tbody className="[font-variant-numeric:tabular-nums]">
          {platforms.map((platform) => (
            <tr key={platform.platform} className="border-b border-line-faint last:border-0">
              <th scope="row" className="py-2 pr-4 font-medium capitalize text-ink-950">
                {platform.platform}
              </th>
              <td className="py-2 pr-4 text-ink-600">{platform.snapshot_count.toLocaleString("en-US")}</td>
              <Cell total={platform.total_likes} average={platform.average_likes} />
              <Cell total={platform.total_comments} average={platform.average_comments} />
              <Cell total={platform.total_shares} average={platform.average_shares} />
              <Cell total={platform.total_impressions} average={platform.average_impressions} last />
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function Cell({ total, average, last }: { total: number; average: number; last?: boolean }) {
  return (
    <td className={last ? "py-2 text-ink-600" : "py-2 pr-4 text-ink-600"}>
      {formatCompactNumber(total)} <span className="text-ink-300">(avg {formatAverage(average)})</span>
    </td>
  );
}
