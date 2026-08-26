"use client";

import { Button } from "@/components/ui/Button";
import { Field, Input } from "@/components/ui/Input";
import { cn } from "@/components/ui/cn";
import { PRESET_LABELS, type DateRangeValue, type DateRangePreset } from "./date-range";

const PRESET_ORDER: Exclude<DateRangePreset, "custom">[] = ["7d", "30d", "90d"];

// One filter row above everything it scopes (interaction.md: "Every
// chart, stat, and table re-renders against the same slice, so the
// numbers always agree") — this same value drives both the brand summary
// and, when a post id is entered, the per-post aggregate/trend below it.
export function DateRangeFilter({
  value,
  onChange,
}: {
  value: DateRangeValue;
  onChange: (next: DateRangeValue) => void;
}) {
  return (
    <div className="flex flex-wrap items-end gap-3">
      <div className="flex items-center gap-1.5" role="group" aria-label="Date range">
        {PRESET_ORDER.map((preset) => (
          <Button
            key={preset}
            type="button"
            size="sm"
            variant={value.preset === preset ? "primary" : "outline"}
            aria-pressed={value.preset === preset}
            onClick={() => onChange({ ...value, preset })}
          >
            {PRESET_LABELS[preset]}
          </Button>
        ))}
        <Button
          type="button"
          size="sm"
          variant={value.preset === "custom" ? "primary" : "outline"}
          aria-pressed={value.preset === "custom"}
          onClick={() => onChange({ ...value, preset: "custom" })}
        >
          Custom
        </Button>
      </div>

      <div className={cn("flex items-end gap-2", value.preset !== "custom" && "opacity-50")}>
        <Field label="Start" htmlFor="analytics-range-start">
          <Input
            id="analytics-range-start"
            type="date"
            value={value.customStart}
            max={value.customEnd}
            disabled={value.preset !== "custom"}
            onChange={(event) => onChange({ ...value, preset: "custom", customStart: event.target.value })}
          />
        </Field>
        <Field label="End" htmlFor="analytics-range-end">
          <Input
            id="analytics-range-end"
            type="date"
            value={value.customEnd}
            min={value.customStart}
            disabled={value.preset !== "custom"}
            onChange={(event) => onChange({ ...value, preset: "custom", customEnd: event.target.value })}
          />
        </Field>
      </div>
    </div>
  );
}
