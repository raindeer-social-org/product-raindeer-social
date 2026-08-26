import { Card } from "@/components/ui/Card";

// Stat tile contract from the dataviz skill (marks-and-anatomy.md):
// label (sentence case, no trailing colon) + value (semibold, auto-compact)
// + an optional secondary line. No delta/sparkline here — the analytics
// endpoints only expose one aggregate window at a time, so there's no
// second period to compare against without fabricating one.
export function StatTile({
  label,
  value,
  secondary,
}: {
  label: string;
  value: string;
  secondary?: string;
}) {
  return (
    <Card className="p-4">
      <p className="text-sm text-slate-500">{label}</p>
      <p className="mt-1 text-2xl font-semibold text-slate-900">{value}</p>
      {secondary ? <p className="mt-0.5 text-xs text-slate-400">{secondary}</p> : null}
    </Card>
  );
}
