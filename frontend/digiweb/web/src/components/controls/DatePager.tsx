"use client";
/**
 * DatePager — capsule Pager with a fixed-width date label and a themed
 * month calendar for bigger jumps. Shared by olympus PipelineDaySelector
 * and BriefsIndex so both surfaces stay 1:1.
 *
 * Chevrons stay in the Pager edge columns; the label opens a Popover
 * calendar (nb-cal) dressed for the glass / term-bg dark chrome.
 */
import { useMemo, useState, type ReactNode } from "react";
import { Popover } from "@base-ui/react/popover";

import { Pager } from "./NavButtons";
import { cx } from "./cx";

const WEEKDAYS = ["Su", "Mo", "Tu", "We", "Th", "Fr", "Sa"] as const;

function ChevronLeftIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M15 18l-6-6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

function ChevronRightIcon() {
  return (
    <svg width="14" height="14" viewBox="0 0 24 24" fill="none" aria-hidden>
      <path
        d="M9 18l6-6-6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** PURE — format YYYY-MM-DD for the capsule label (UTC noon). */
export function formatDatePagerLabel(iso: string): string {
  if (!iso) return "—";
  try {
    const d = new Date(`${iso}T12:00:00Z`);
    return d.toLocaleDateString("en-US", {
      weekday: "short",
      month: "short",
      day: "numeric",
      year: "numeric",
      timeZone: "UTC",
    });
  } catch {
    return iso;
  }
}

function parseIso(iso: string): { y: number; m: number; d: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  return { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) };
}

function toIso(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, "0")}-${String(d).padStart(2, "0")}`;
}

function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

function monthStartWeekday(y: number, m: number): number {
  // JS: 0 = Sunday — matches WEEKDAYS.
  return new Date(Date.UTC(y, m - 1, 1)).getUTCDay();
}

function shiftMonth(y: number, m: number, delta: number): { y: number; m: number } {
  const idx = y * 12 + (m - 1) + delta;
  return { y: Math.floor(idx / 12), m: (idx % 12) + 1 };
}

function monthLabel(y: number, m: number): string {
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString("en-US", {
    month: "long",
    year: "numeric",
    timeZone: "UTC",
  });
}

export type DatePagerProps = {
  value: string;
  onChange: (iso: string) => void;
  onPrev?: () => void;
  onNext?: () => void;
  prevDisabled?: boolean;
  nextDisabled?: boolean;
  prevAriaLabel?: string;
  nextAriaLabel?: string;
  /** Accessible name for the date label / calendar trigger. */
  labelAriaLabel?: string;
  min?: string;
  max?: string;
  /**
   * When set, only these YYYY-MM-DD keys are selectable (pipeline discrete
   * runs). When omitted, any day inside min/max is allowed (briefs gaps).
   */
  allowedDates?: readonly string[];
  formatLabel?: (iso: string) => string;
  prevLabel?: ReactNode;
  nextLabel?: ReactNode;
  className?: string;
  disabled?: boolean;
};

export function DatePager({
  value,
  onChange,
  onPrev,
  onNext,
  prevDisabled,
  nextDisabled,
  prevAriaLabel = "Previous day",
  nextAriaLabel = "Next day",
  labelAriaLabel = "Pick date",
  min,
  max,
  allowedDates,
  formatLabel = formatDatePagerLabel,
  prevLabel = <ChevronLeftIcon />,
  nextLabel = <ChevronRightIcon />,
  className,
  disabled,
}: DatePagerProps) {
  const [open, setOpen] = useState(false);
  const parsed = parseIso(value);
  const initialMonth = parsed ?? { y: new Date().getUTCFullYear(), m: new Date().getUTCMonth() + 1 };
  const [view, setView] = useState(initialMonth);

  const allowed = useMemo(
    () => (allowedDates ? new Set(allowedDates) : null),
    [allowedDates],
  );

  const isEnabled = (iso: string): boolean => {
    if (min && iso < min) return false;
    if (max && iso > max) return false;
    if (allowed && !allowed.has(iso)) return false;
    return true;
  };

  const minParsed = min ? parseIso(min) : null;
  const maxParsed = max ? parseIso(max) : null;
  const canPrevMonth =
    !minParsed || view.y > minParsed.y || (view.y === minParsed.y && view.m > minParsed.m);
  const canNextMonth =
    !maxParsed || view.y < maxParsed.y || (view.y === maxParsed.y && view.m < maxParsed.m);

  const weeks = useMemo(() => {
    const dim = daysInMonth(view.y, view.m);
    const start = monthStartWeekday(view.y, view.m);
    const out: Array<{ iso: string; day: number } | null> = [];
    for (let i = 0; i < start; i++) out.push(null);
    for (let day = 1; day <= dim; day++) {
      out.push({ iso: toIso(view.y, view.m, day), day });
    }
    while (out.length % 7 !== 0) out.push(null);
    const rows: Array<Array<{ iso: string; day: number } | null>> = [];
    for (let i = 0; i < out.length; i += 7) rows.push(out.slice(i, i + 7));
    return rows;
  }, [view.y, view.m]);

  const onOpenChange = (next: boolean) => {
    setOpen(next);
    if (next) {
      const p = parseIso(value);
      if (p) setView({ y: p.y, m: p.m });
    }
  };

  const pick = (iso: string) => {
    if (!isEnabled(iso)) return;
    onChange(iso);
    setOpen(false);
  };

  return (
    <Pager
      dress="capsule"
      className={cx("nb-pager--date", className)}
      prevLabel={prevLabel}
      nextLabel={nextLabel}
      prevAriaLabel={prevAriaLabel}
      nextAriaLabel={nextAriaLabel}
      prevDisabled={disabled || prevDisabled}
      nextDisabled={disabled || nextDisabled}
      onPrev={onPrev}
      onNext={onNext}
    >
      <Popover.Root open={open} onOpenChange={onOpenChange}>
        <Popover.Trigger
          type="button"
          className="nb-pager-date"
          aria-label={labelAriaLabel}
          disabled={disabled}
        >
          <span className="nb-pager-date-text">{formatLabel(value)}</span>
        </Popover.Trigger>
        <Popover.Portal>
          <Popover.Positioner className="isolate z-50 outline-none" side="bottom" sideOffset={6} align="center">
            <Popover.Popup
              data-slot="date-pager-calendar"
              className="nb-cal ctl-pop z-50 origin-(--transform-origin) outline-none"
            >
              <div className="nb-cal-head">
                <button
                  type="button"
                  className="nb-cal-nav"
                  aria-label="Previous month"
                  disabled={!canPrevMonth}
                  onClick={() => setView((v) => shiftMonth(v.y, v.m, -1))}
                >
                  <ChevronLeftIcon />
                </button>
                <div className="nb-cal-title">{monthLabel(view.y, view.m)}</div>
                <button
                  type="button"
                  className="nb-cal-nav"
                  aria-label="Next month"
                  disabled={!canNextMonth}
                  onClick={() => setView((v) => shiftMonth(v.y, v.m, 1))}
                >
                  <ChevronRightIcon />
                </button>
              </div>
              <div className="nb-cal-weekdays" aria-hidden>
                {WEEKDAYS.map((w) => (
                  <span key={w} className="nb-cal-weekday">
                    {w}
                  </span>
                ))}
              </div>
              <div className="nb-cal-grid" role="grid" aria-label={monthLabel(view.y, view.m)}>
                {weeks.map((week, w) => (
                  <div key={`w-${w}`} role="row" className="nb-cal-row">
                    {week.map((cell, i) =>
                      cell ? (
                        <button
                          key={cell.iso}
                          type="button"
                          role="gridcell"
                          className={cx(
                            "nb-cal-day",
                            cell.iso === value && "nb-cal-day--selected",
                            !isEnabled(cell.iso) && "nb-cal-day--muted",
                          )}
                          aria-selected={cell.iso === value}
                          disabled={!isEnabled(cell.iso)}
                          onClick={() => pick(cell.iso)}
                        >
                          {cell.day}
                        </button>
                      ) : (
                        <span
                          key={`e-${w}-${i}`}
                          role="gridcell"
                          className="nb-cal-day nb-cal-day--empty"
                          aria-hidden
                        />
                      ),
                    )}
                  </div>
                ))}
              </div>
            </Popover.Popup>
          </Popover.Positioner>
        </Popover.Portal>
      </Popover.Root>
    </Pager>
  );
}
