import { cn } from "../../lib/utils";

export type KpiTone = "pos" | "neg";

export type KpiCell = {
  /** Visible cell label. */
  label: string;
  /** The figure as it should read. `null`, `undefined`, `""` and non-finite
   *  numbers render the missing mark — never a zero the data did not contain. */
  value: string | number | null | undefined;
  /** Money semantics — `--up` / `--down`, signed P&L only. */
  tone?: KpiTone;
  /** Secondary line under the figure. */
  note?: string;
  /** Accessible name when the figure alone does not read as a value to a
   *  screen reader (a glyph, a dash, a bare ratio). Defaults to the visible text. */
  valueLabel?: string;
};

export type KpiGridProps = {
  items: KpiCell[];
  /** Mark shown in place of a figure the payload did not carry. */
  missing?: string;
  className?: string;
};

const read = (value: KpiCell["value"], missing: string): { text: string; absent: boolean } => {
  if (value == null) return { text: missing, absent: true };
  if (typeof value === "number") {
    return Number.isFinite(value)
      ? { text: String(value), absent: false }
      : { text: missing, absent: true };
  }
  const text = value.trim();
  return text ? { text, absent: false } : { text: missing, absent: true };
};

/**
 * KpiGrid — a dense label / figure grid on hairlines, one `<dl>` so each figure
 * is announced with its label. Figures are tabular, so a column of them lines up
 * digit for digit. No motion, so reduced-motion needs no special case.
 */
export function KpiGrid({ items, missing = "—", className }: KpiGridProps) {
  return (
    <dl
      className={cn(
        "grid grid-cols-[repeat(auto-fit,minmax(8.5rem,1fr))] rounded-none border-t border-l border-hair",
        className,
      )}
    >
      {items.map((item) => {
        const value = read(item.value, missing);
        return (
          <div key={item.label} className="border-r border-b border-hair px-3 py-2">
            <dt className="font-mono text-[0.64rem] tracking-[0.08em] text-ink-mute uppercase">
              {item.label}
            </dt>
            <dd
              data-state={value.absent ? "missing" : "present"}
              aria-label={item.valueLabel}
              className={cn(
                "mt-1 font-mono text-[1.15rem] leading-none [font-variant-numeric:tabular-nums]",
                value.absent ? "text-ink-mute" : "text-ink",
                item.tone === "pos" && !value.absent && "text-up",
                item.tone === "neg" && !value.absent && "text-down",
              )}
            >
              {value.text}
              {item.note ? (
                <span className="mt-1 block font-mono text-[0.68rem] text-ink-mute">
                  {item.note}
                </span>
              ) : null}
            </dd>
          </div>
        );
      })}
    </dl>
  );
}
