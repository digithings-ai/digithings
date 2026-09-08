'use client';

/**
 * Compact board-date range filter for the Trades tab.
 * Reuses DigiWeb DatePager calendar chrome (`.nb-cal`) — click start, then end.
 * No shared date-range picker exists in digiweb/dashboard yet.
 */
import { useEffect, useMemo, useRef, useState } from 'react';

const WEEKDAYS = ['Su', 'Mo', 'Tu', 'We', 'Th', 'Fr', 'Sa'] as const;

function parseIso(iso: string): { y: number; m: number; d: number } | null {
  const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso);
  if (!m) return null;
  return { y: Number(m[1]), m: Number(m[2]), d: Number(m[3]) };
}

function toIso(y: number, m: number, d: number): string {
  return `${y}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`;
}

function daysInMonth(y: number, m: number): number {
  return new Date(Date.UTC(y, m, 0)).getUTCDate();
}

function monthStartWeekday(y: number, m: number): number {
  return new Date(Date.UTC(y, m - 1, 1)).getUTCDay();
}

function shiftMonth(y: number, m: number, delta: number): { y: number; m: number } {
  const idx = y * 12 + (m - 1) + delta;
  return { y: Math.floor(idx / 12), m: (idx % 12) + 1 };
}

function monthLabel(y: number, m: number): string {
  return new Date(Date.UTC(y, m - 1, 1)).toLocaleDateString('en-US', {
    month: 'long',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

/** Compact label for a YYYY-MM-DD board date. */
export function formatBoardDateShort(iso: string): string {
  const p = parseIso(iso);
  if (!p) return iso;
  return new Date(`${iso}T12:00:00Z`).toLocaleDateString('en-US', {
    month: 'short',
    day: 'numeric',
    year: 'numeric',
    timeZone: 'UTC',
  });
}

export function formatBoardRangeLabel(from: string | null, to: string | null): string {
  if (from === null && to === null) return 'All boards';
  if (from !== null && to !== null && from === to) return formatBoardDateShort(from);
  if (from !== null && to !== null) {
    return `${formatBoardDateShort(from)} – ${formatBoardDateShort(to)}`;
  }
  if (from !== null) return `From ${formatBoardDateShort(from)}`;
  return `Through ${formatBoardDateShort(to!)}`;
}

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
        d="M9 18l6-6 6-6"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export type BoardDateRangeFilterProps = {
  /** Available board dates (any order). */
  boards: readonly string[];
  boardFrom: string | null;
  boardTo: string | null;
  onChange: (from: string | null, to: string | null) => void;
};

export default function BoardDateRangeFilter({
  boards,
  boardFrom,
  boardTo,
  onChange,
}: BoardDateRangeFilterProps) {
  const [open, setOpen] = useState(false);
  /** First click while building a new range; null when idle. */
  const [pendingStart, setPendingStart] = useState<string | null>(null);
  const rootRef = useRef<HTMLDivElement | null>(null);

  const allowed = useMemo(() => new Set(boards), [boards]);
  const sortedAsc = useMemo(() => [...boards].sort((a, b) => a.localeCompare(b)), [boards]);
  const minDate = sortedAsc[0];
  const maxDate = sortedAsc[sortedAsc.length - 1];

  const anchorIso = boardTo ?? boardFrom ?? maxDate ?? '';
  const initial = parseIso(anchorIso) ?? {
    y: new Date().getUTCFullYear(),
    m: new Date().getUTCMonth() + 1,
  };
  const [view, setView] = useState(initial);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (!rootRef.current?.contains(e.target as Node)) {
        setOpen(false);
        setPendingStart(null);
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const openPicker = () => {
    const p = parseIso(anchorIso);
    if (p) setView({ y: p.y, m: p.m });
    setPendingStart(null);
    setOpen((v) => !v);
  };

  const isEnabled = (iso: string): boolean => allowed.has(iso);

  const inCommittedRange = (iso: string): boolean => {
    if (boardFrom === null || boardTo === null) return false;
    return iso >= boardFrom && iso <= boardTo;
  };

  const isEndpoint = (iso: string): boolean =>
    iso === boardFrom || iso === boardTo || iso === pendingStart;

  const pick = (iso: string) => {
    if (!isEnabled(iso)) return;
    if (pendingStart === null) {
      setPendingStart(iso);
      return;
    }
    const from = pendingStart <= iso ? pendingStart : iso;
    const to = pendingStart <= iso ? iso : pendingStart;
    onChange(from, to);
    setPendingStart(null);
    setOpen(false);
  };

  const clear = () => {
    onChange(null, null);
    setPendingStart(null);
    setOpen(false);
  };

  const minParsed = minDate ? parseIso(minDate) : null;
  const maxParsed = maxDate ? parseIso(maxDate) : null;
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

  const hasRange = boardFrom !== null || boardTo !== null;
  const label = formatBoardRangeLabel(boardFrom, boardTo);
  const hint =
    pendingStart !== null
      ? `Start ${formatBoardDateShort(pendingStart)} — click end date`
      : 'Click start date, then end date';

  return (
    <div ref={rootRef} className="relative">
      <div className="flex items-center gap-1">
        <button
          type="button"
          aria-expanded={open}
          aria-haspopup="dialog"
          aria-label="Filter by board date range"
          onClick={openPicker}
          disabled={boards.length === 0}
          className={`border px-2.5 py-1 text-[11px] font-medium transition-colors ${
            hasRange || open
              ? 'border-accent/40 bg-accent/15 text-accent'
              : 'border-hair text-ink-mute hover:text-ink'
          }`}
        >
          {label}
        </button>
        {hasRange ? (
          <button
            type="button"
            aria-label="Clear board date range"
            onClick={clear}
            className="border border-hair px-1.5 py-1 text-[11px] text-ink-mute hover:text-ink"
          >
            Clear
          </button>
        ) : null}
      </div>
      {open ? (
        <div
          role="dialog"
          aria-label="Board date range"
          data-testid="board-date-range-calendar"
          className="nb-cal ctl-pop absolute left-0 top-full z-50 mt-1"
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
          <p className="mb-2 text-center font-mono text-[10px] text-ink-mute">{hint}</p>
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
                      className={[
                        'nb-cal-day',
                        isEndpoint(cell.iso) ? 'nb-cal-day--selected' : '',
                        !isEndpoint(cell.iso) && inCommittedRange(cell.iso)
                          ? 'bg-accent/10 text-ink'
                          : '',
                        !isEnabled(cell.iso) ? 'nb-cal-day--muted' : '',
                      ]
                        .filter(Boolean)
                        .join(' ')}
                      aria-selected={isEndpoint(cell.iso)}
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
        </div>
      ) : null}
    </div>
  );
}
