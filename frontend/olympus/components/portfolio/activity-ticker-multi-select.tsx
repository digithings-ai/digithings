'use client';

import { useEffect, useId, useMemo, useRef, useState } from 'react';
import { ChevronDown } from 'lucide-react';

/**
 * Searchable multi-select for tickers (same interaction pattern as NAV comparables).
 * Empty selection = no restriction (all tickers).
 */
export function ActivityTickerMultiSelect({
  universe,
  selected,
  onAdd,
  onRemove,
}: {
  universe: string[];
  selected: string[];
  onAdd: (ticker: string) => void;
  onRemove: (ticker: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [q, setQ] = useState('');
  const rootRef = useRef<HTMLDivElement>(null);
  const listboxId = useId();

  const filtered = useMemo(() => {
    const qq = q.trim().toUpperCase();
    if (!qq) return universe;
    return universe.filter((t) => t.includes(qq));
  }, [universe, q]);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => {
      if (rootRef.current && !rootRef.current.contains(e.target as Node)) {
        setOpen(false);
        setQ('');
      }
    };
    document.addEventListener('mousedown', onDoc);
    return () => document.removeEventListener('mousedown', onDoc);
  }, [open]);

  const toggleOpen = () => {
    if (open) {
      setOpen(false);
      setQ('');
    } else {
      setQ('');
      setOpen(true);
    }
  };

  return (
    <div ref={rootRef} className="flex flex-wrap items-center gap-2">
      {selected.map((t) => (
        <span
          key={t}
          className="inline-flex items-center gap-0.5 pl-2 pr-1 py-0.5 rounded-md text-[11px] font-mono font-medium border border-accent/35 bg-accent/10 text-accent"
        >
          {t}
          <button
            type="button"
            onClick={() => onRemove(t)}
            className="p-0.5 rounded hover:bg-white/10 text-ink-soft hover:text-ink leading-none"
            aria-label={`Remove ${t}`}
          >
            ×
          </button>
        </span>
      ))}

      <div className="relative">
        <button
          type="button"
          onClick={toggleOpen}
          className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-medium border border-hair bg-term-bg text-ink-soft hover:border-accent/40 hover:text-ink transition-colors"
          aria-expanded={open ? 'true' : 'false'}
          aria-haspopup="listbox"
          aria-controls={listboxId}
        >
          Tickers
          <ChevronDown size={14} className={`opacity-70 transition-transform ${open ? 'rotate-180' : ''}`} />
        </button>

        {open && (
          <div
            className="absolute left-0 top-full z-[60] mt-1 w-[min(100vw-2rem,18rem)] rounded-lg border border-hair bg-term-bg shadow-xl overflow-hidden"
          >
            <input
              type="search"
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Search tickers…"
              aria-label="Search tickers"
              className="w-full px-2.5 py-2 text-sm bg-bg border-b border-hair text-ink placeholder:text-ink-mute focus:outline-none focus:ring-1 focus:ring-inset focus:ring-accent/30"
              autoComplete="off"
              autoFocus
            />
            <div id={listboxId} className="max-h-52 overflow-y-auto py-1">
              {filtered.length === 0 ? (
                <div role="status" className="text-xs text-ink-mute px-3 py-4 text-center">
                  No matches
                </div>
              ) : (
                <div role="listbox" aria-label="Tickers" aria-multiselectable="true">
                  {filtered.map((t) => {
                    const on = selected.includes(t);
                    return (
                      <button
                        key={t}
                        type="button"
                        role="option"
                        aria-selected={on ? 'true' : 'false'}
                        onClick={() => {
                          if (on) onRemove(t);
                          else onAdd(t);
                        }}
                        className={`w-full text-left px-3 py-1.5 text-xs font-mono transition-colors ${
                          on
                            ? 'bg-accent/15 text-accent'
                            : 'text-ink-soft hover:bg-white/[0.06] hover:text-ink'
                        }`}
                      >
                        {t}
                      </button>
                    );
                  })}
                </div>
              )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}
