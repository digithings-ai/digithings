"use client";

import { useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";

/**
 * Command palette — the dev-tool ⌘K signature: a fuzzy command bar over a
 * blurred page, opened by keystroke or the trigger button. Actions are grouped,
 * each row carries a livery dot and a shortcut, and arrow keys drive a flat
 * active index across the groups. Rendered into a portal on the body.
 */
type Command = { group: string; label: string; hint: string; livery?: string };

const COMMANDS: Command[] = [
  { group: "Actions", label: "Run a backtest", hint: "B", livery: "digiquant" },
  { group: "Actions", label: "Ask digichat", hint: "C", livery: "digichat" },
  { group: "Actions", label: "Issue an API key", hint: "K", livery: "digikey" },
  { group: "Actions", label: "Search the corpus", hint: "/", livery: "digisearch" },
  { group: "Navigate", label: "Open olympus", hint: "O", livery: "atlas" },
  { group: "Navigate", label: "Open the vault", hint: "V", livery: "digivault" },
  { group: "Navigate", label: "View changelog", hint: "L" },
  { group: "Navigate", label: "Toggle theme", hint: "T" },
];

export function CommandPaletteReference() {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const inputRef = useRef<HTMLInputElement | null>(null);

  const filtered = COMMANDS.filter((c) => c.label.toLowerCase().includes(query.toLowerCase()));

  const openPalette = () => {
    setQuery("");
    setActive(0);
    setOpen(true);
  };

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "k") {
        e.preventDefault();
        if (open) setOpen(false);
        else openPalette();
        return;
      }
      if (!open) return;
      if (e.key === "Escape") setOpen(false);
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(filtered.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        setOpen(false);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, filtered.length]);

  useEffect(() => {
    // focus the input after the dialog paints (DOM only — no state here)
    if (open) requestAnimationFrame(() => inputRef.current?.focus());
  }, [open]);

  // group the filtered list, preserving order, with a flat index for the active row
  let flat = -1;
  const groups = Array.from(new Set(filtered.map((c) => c.group)));

  return (
    <section className="section-block command-palette">
      <p className="kicker">{"// command palette"}</p>
      <h2 className="title">Everything, a keystroke away.</h2>
      <p className="section-copy">
        The dev-tool signature: <kbd className="kbd">⌘</kbd>
        <kbd className="kbd">K</kbd> opens a fuzzy command bar over a blurred page. Grouped actions,
        a livery dot per module, a shortcut on each row, and arrow-key navigation. Try it — press
        ⌘K (or Ctrl K), or the button.
      </p>

      <button type="button" className="cp-trigger" onClick={openPalette}>
        <span>Search commands…</span>
        <span className="inline-flex gap-[0.2rem]">
          <kbd className="kbd">⌘</kbd>
          <kbd className="kbd">K</kbd>
        </span>
      </button>

      {open
        ? createPortal(
            <div className="cp-overlay" role="dialog" aria-label="Command palette" aria-modal="true">
              <div className="cp-scrim" onClick={() => setOpen(false)} aria-hidden="true" />
              <div className="cp-panel">
                <div className="cp-input-row">
                  <span className="cp-search-glyph" aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.6">
                      <circle cx="11" cy="11" r="7" />
                      <path d="M20 20l-3.5-3.5" strokeLinecap="round" />
                    </svg>
                  </span>
                  <input
                    ref={inputRef}
                    className="cp-input"
                    placeholder="Type a command or search…"
                    value={query}
                    onChange={(e) => {
                      setQuery(e.target.value);
                      setActive(0);
                    }}
                  />
                  <kbd className="kbd">esc</kbd>
                </div>

                <div className="cp-results">
                  {filtered.length === 0 ? (
                    <p className="cp-empty">No commands match “{query}”.</p>
                  ) : (
                    groups.map((g) => (
                      <div key={g} className="cp-group">
                        <p className="cp-group-label">{g}</p>
                        {filtered
                          .filter((c) => c.group === g)
                          .map((c) => {
                            flat += 1;
                            const idx = flat;
                            return (
                              <button
                                key={c.label}
                                type="button"
                                className={`cp-row${idx === active ? " on" : ""}${c.livery ? ` accent-${c.livery}` : ""}`}
                                onMouseEnter={() => setActive(idx)}
                                onClick={() => setOpen(false)}
                              >
                                <span className="cp-dot" aria-hidden="true" />
                                <span className="cp-label">{c.label}</span>
                                <kbd className="kbd cp-row-key">{c.hint}</kbd>
                              </button>
                            );
                          })}
                      </div>
                    ))
                  )}
                </div>

                <div className="cp-foot" aria-hidden="true">
                  <span>
                    <kbd className="kbd">↑</kbd>
                    <kbd className="kbd">↓</kbd> navigate
                  </span>
                  <span>
                    <kbd className="kbd">↵</kbd> open
                  </span>
                  <span>
                    <kbd className="kbd">esc</kbd> close
                  </span>
                </div>
              </div>
            </div>,
            document.body,
          )
        : null}
    </section>
  );
}
