'use client';

import { useState } from 'react';

export type MiniCalendarRunKind = 'baseline' | 'delta' | 'unknown';

export interface MiniCalendarProps {
  dates: string[];
  runKindByDate: Map<string, MiniCalendarRunKind>;
  selected: string | null;
  onSelect: (date: string) => void;
}

export default function MiniCalendar({ dates, runKindByDate, selected, onSelect }: MiniCalendarProps) {
  const [viewMonth, setViewMonth] = useState<{ year: number; month: number }>(() => {
    const today = new Date();
    return { year: today.getFullYear(), month: today.getMonth() };
  });

  const { year, month } = viewMonth;
  const dateSet = new Set(dates);
  const first = new Date(year, month, 1);
  const startDay = first.getDay();
  const daysInMonth = new Date(year, month + 1, 0).getDate();
  const cells: (number | null)[] = [];

  for (let i = 0; i < startDay; i++) cells.push(null);
  for (let d = 1; d <= daysInMonth; d++) cells.push(d);

  function pad(n: number): string {
    return String(n).padStart(2, '0');
  }

  function prev() {
    setViewMonth((v) =>
      v.month === 0 ? { year: v.year - 1, month: 11 } : { ...v, month: v.month - 1 }
    );
  }
  function next() {
    setViewMonth((v) =>
      v.month === 11 ? { year: v.year + 1, month: 0 } : { ...v, month: v.month + 1 }
    );
  }

  const monthNames = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

  return (
    <div className="glass-card p-4">
      <div className="flex items-center justify-between mb-3">
        <button type="button" onClick={prev} className="text-ink-mute hover:text-ink text-sm px-1">
          ‹
        </button>
        <span className="text-sm font-medium">
          {monthNames[month]} {year}
        </span>
        <button type="button" onClick={next} className="text-ink-mute hover:text-ink text-sm px-1">
          ›
        </button>
      </div>
      <div className="grid grid-cols-7 gap-1 text-center text-[10px]">
        {['S', 'M', 'T', 'W', 'T', 'F', 'S'].map((d, i) => (
          <div key={i} className="text-ink-mute pb-1">
            {d}
          </div>
        ))}
        {cells.map((day, i) => {
          if (!day) return <div key={`e${i}`} />;
          const iso = `${year}-${pad(month + 1)}-${pad(day)}`;
          const has = dateSet.has(iso);
          const sel = iso === selected;
          const kind = has ? runKindByDate.get(iso) ?? 'unknown' : 'unknown';

          const dayBtn = [
            'w-7 h-7 rounded-full text-[11px] flex items-center justify-center transition-colors',
            !has ? 'text-ink-mute/30 cursor-default' : 'cursor-pointer',
          ];

          if (sel) {
            dayBtn.push('bg-accent text-on-accent font-bold ring-2 ring-accent ring-offset-2 ring-offset-bg');
          } else if (has) {
            if (kind === 'baseline') {
              dayBtn.push('bg-warn/25 text-warn border border-warn/50 hover:bg-warn/35');
            } else if (kind === 'delta') {
              dayBtn.push('text-accent hover:bg-accent/20');
            } else {
              dayBtn.push('text-ink-soft border border-hair/80 hover:bg-white/[0.06]');
            }
          }

          return (
            <button
              key={i}
              type="button"
              disabled={!has}
              onClick={() => has && onSelect(iso)}
              className={dayBtn.join(' ')}
            >
              {day}
            </button>
          );
        })}
      </div>
      <div className="mt-3 pt-3 border-t border-hair space-y-1.5 text-[10px] text-ink-mute">
        <p className="uppercase tracking-wider">Run type</p>
        <div className="flex flex-col gap-1">
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-warn/80 border border-warn" />
            <span>Baseline</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full bg-accent/80" />
            <span>Delta</span>
          </div>
          <div className="flex items-center gap-2">
            <span className="w-2.5 h-2.5 rounded-full border border-hair bg-term-bg" />
            <span>Unknown</span>
          </div>
        </div>
      </div>
    </div>
  );
}
