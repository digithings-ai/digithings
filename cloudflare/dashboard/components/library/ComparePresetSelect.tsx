'use client';

import { Select, SelectContent, SelectItem, SelectTrigger } from '@digithings/web/ui';

export type ComparePreset = 'previous' | 'delta_baseline';

/**
 * Shared compare-preset control for the library diff views (DigestDocumentView
 * and GenericDiffDocumentView). Wave 3 (#4206): the two hand-rolled listbox
 * dropdowns that used to live in each view were the same surface implemented
 * twice; this is the single kit `Select` both now render.
 *
 * The trigger shows the caller's summary label (including the custom-date
 * readout) via a manual span rather than `SelectValue`, because a custom date
 * is not a selectable preset item — `value` stays null in that case and the
 * span carries the label.
 */
export function ComparePresetSelect({
  summaryLabel,
  value,
  canPrevious,
  canBaseline,
  previousLabel,
  baselineLabel,
  hint,
  ariaLabel,
  onSelectPreset,
}: {
  summaryLabel: string;
  value: ComparePreset | null;
  canPrevious: boolean;
  canBaseline: boolean;
  previousLabel: string;
  baselineLabel: string;
  hint: string;
  ariaLabel: string;
  onSelectPreset: (preset: ComparePreset) => void;
}) {
  return (
    <Select
      value={value}
      onValueChange={(v) => {
        if (v === 'previous' || v === 'delta_baseline') onSelectPreset(v);
      }}
    >
      <SelectTrigger
        aria-label={ariaLabel}
        title={hint}
        className="h-auto w-fit rounded-none border-hair bg-term-bg px-2.5 py-1 text-xs font-medium text-ink-soft hover:border-accent/40 hover:text-ink"
      >
        <span className="max-w-[min(100vw-8rem,14rem)] truncate">{summaryLabel}</span>
      </SelectTrigger>
      <SelectContent align="start" alignItemWithTrigger={false}>
        <SelectItem value="previous" disabled={!canPrevious}>
          {previousLabel}
        </SelectItem>
        <SelectItem value="delta_baseline" disabled={!canBaseline}>
          {baselineLabel}
        </SelectItem>
      </SelectContent>
    </Select>
  );
}
