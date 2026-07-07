"use client";

import { useEffect, useRef, useState } from "react";

type Option = { id: string; group: string; label: string; note: string; pf: string; livery: string };

const OPTIONS: Option[] = [
  { id: "trend_xsec", group: "Momentum", label: "trend_xsec", note: "cross-sectional", pf: "2.31", livery: "digiquant" },
  { id: "breakout", group: "Momentum", label: "breakout", note: "volatility breakout", pf: "1.94", livery: "digiquant" },
  { id: "mean_rev", group: "Mean reversion", label: "mean_rev", note: "intraday", pf: "2.58", livery: "atlas" },
  { id: "pairs", group: "Mean reversion", label: "pairs", note: "cointegrated legs", pf: "1.71", livery: "atlas" },
  { id: "carry", group: "Carry", label: "carry", note: "funding-rate", pf: "3.02", livery: "hermes" },
];

export function DropdownReference() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(OPTIONS[0].id);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const current = OPTIONS.find((o) => o.id === selected) ?? OPTIONS[0];
  const filtered = OPTIONS.filter(
    (o) =>
      o.label.toLowerCase().includes(query.toLowerCase()) ||
      o.note.toLowerCase().includes(query.toLowerCase()),
  );
  const groups = Array.from(new Set(filtered.map((o) => o.group)));
  // Navigable order mirrors the grouped render order below, so ArrowUp/Down and
  // Enter stay aligned even if OPTIONS is reordered to interleave groups.
  const ordered = groups.flatMap((g) => filtered.filter((o) => o.group === g));

  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(ordered.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter" && ordered[active]) {
        e.preventDefault();
        setSelected(ordered[active].id);
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, active, ordered]);

  const openMenu = () => {
    setQuery("");
    // index into the same grouped order the pane renders, not raw OPTIONS order
    const allGroups = Array.from(new Set(OPTIONS.map((o) => o.group)));
    const allOrdered = allGroups.flatMap((g) => OPTIONS.filter((o) => o.group === g));
    setActive(Math.max(0, allOrdered.findIndex((o) => o.id === selected)));
    setOpen(true);
    requestAnimationFrame(() => inputRef.current?.focus());
  };

  let flat = -1;

  return (
    <section className="section-block">
      <p className="kicker">{"// dropdown"}</p>
      <h2 className="title">A pane, not a list.</h2>
      <p className="section-copy">
        A custom select whose pane is its own surface: an in-pane filter, grouped options, rich
        rows (livery dot, description, a profit-factor badge), and a footer action. Type to filter,
        arrow-keys to move, Enter to choose, click-outside or Escape to close.
      </p>

      <div className="ctl-dropdown" ref={wrapRef}>
        <button
          type="button"
          className={`dd-trigger${open ? " open" : ""}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={() => (open ? setOpen(false) : openMenu())}
        >
          <span className="dd-value">
            <span className="dd-label">{current.label}</span>
            <span className="dd-note">{current.note}</span>
          </span>
          <span className="dd-caret" aria-hidden="true" />
        </button>

        {open ? (
          <div className="dd-menu">
            <div className="dd-search-row">
              <span className="dd-search-glyph" aria-hidden="true">
                <svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" strokeWidth="1.6">
                  <circle cx="11" cy="11" r="7" />
                  <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
                </svg>
              </span>
              <input
                ref={inputRef}
                className="dd-search"
                placeholder="Filter strategies…"
                value={query}
                onChange={(e) => {
                  setQuery(e.target.value);
                  setActive(0);
                }}
              />
            </div>

            <div className="dd-scroll" role="listbox" aria-label="Strategy">
              {filtered.length === 0 ? (
                <p className="dd-empty">No strategy matches “{query}”.</p>
              ) : (
                groups.map((g) => (
                  <div key={g} className="dd-group">
                    <p className="dd-group-label">{g}</p>
                    {filtered
                      .filter((o) => o.group === g)
                      .map((o) => {
                        flat += 1;
                        const idx = flat;
                        return (
                          <button
                            key={o.id}
                            type="button"
                            role="option"
                            aria-selected={o.id === selected}
                            className={`dd-option accent-${o.livery}${idx === active ? " active" : ""}${o.id === selected ? " selected" : ""}`}
                            onMouseEnter={() => setActive(idx)}
                            onClick={() => {
                              setSelected(o.id);
                              setOpen(false);
                            }}
                          >
                            <span className="dd-dot" aria-hidden="true" />
                            <span className="dd-opt-label">{o.label}</span>
                            <span className="dd-opt-note">{o.note}</span>
                            <span className="dd-metric">PF {o.pf}</span>
                            {o.id === selected ? (
                              <span className="dd-check" aria-hidden="true">
                                ✓
                              </span>
                            ) : null}
                          </button>
                        );
                      })}
                  </div>
                ))
              )}
            </div>

            <div className="dd-footer">
              <button type="button" className="dd-footer-action" onClick={() => setOpen(false)}>
                <span aria-hidden="true">+</span> New strategy…
              </button>
            </div>
          </div>
        ) : null}
      </div>
    </section>
  );
}
