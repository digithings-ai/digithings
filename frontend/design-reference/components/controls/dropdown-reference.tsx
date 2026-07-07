"use client";

import { useEffect, useRef, useState } from "react";

const OPTIONS = [
  { id: "trend_xsec", label: "trend_xsec", note: "cross-sectional momentum" },
  { id: "mean_rev", label: "mean_rev", note: "intraday mean reversion" },
  { id: "carry", label: "carry", note: "funding-rate carry" },
  { id: "breakout", label: "breakout", note: "volatility breakout" },
];

export function DropdownReference() {
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(OPTIONS[0].id);
  const [active, setActive] = useState(0);
  const wrapRef = useRef<HTMLDivElement | null>(null);

  const current = OPTIONS.find((o) => o.id === selected) ?? OPTIONS[0];

  // click-outside + Escape close
  useEffect(() => {
    if (!open) return;
    const onDown = (e: MouseEvent) => {
      if (wrapRef.current && !wrapRef.current.contains(e.target as Node)) setOpen(false);
    };
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOpen(false);
      else if (e.key === "ArrowDown") {
        e.preventDefault();
        setActive((i) => Math.min(OPTIONS.length - 1, i + 1));
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setActive((i) => Math.max(0, i - 1));
      } else if (e.key === "Enter") {
        e.preventDefault();
        setSelected(OPTIONS[active].id);
        setOpen(false);
      }
    };
    document.addEventListener("mousedown", onDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open, active]);

  const toggle = () => {
    setActive(OPTIONS.findIndex((o) => o.id === selected));
    setOpen((v) => !v);
  };

  return (
    <section className="section-block">
      <p className="kicker">{"// dropdown"}</p>
      <h2 className="title">Select, with keyboard.</h2>
      <p className="section-copy">
        A custom select — not the native control — so the menu wears the system grammar: hairline
        surface, a check on the chosen row, arrow-key navigation, click-outside and Escape to
        close. The trigger shows the current value; the accent marks the selection.
      </p>

      <div className="ctl-dropdown" ref={wrapRef}>
        <button
          type="button"
          className={`dd-trigger${open ? " open" : ""}`}
          aria-haspopup="listbox"
          aria-expanded={open}
          onClick={toggle}
        >
          <span className="dd-value">
            <span className="dd-label">{current.label}</span>
            <span className="dd-note">{current.note}</span>
          </span>
          <span className="dd-caret" aria-hidden="true" />
        </button>

        {open ? (
          <ul className="dd-menu" role="listbox" aria-label="Strategy">
            {OPTIONS.map((o, i) => (
              <li key={o.id}>
                <button
                  type="button"
                  role="option"
                  aria-selected={o.id === selected}
                  className={`dd-option${i === active ? " active" : ""}${o.id === selected ? " selected" : ""}`}
                  onMouseEnter={() => setActive(i)}
                  onClick={() => {
                    setSelected(o.id);
                    setOpen(false);
                  }}
                >
                  <span className="dd-check" aria-hidden="true">
                    {o.id === selected ? "✓" : ""}
                  </span>
                  <span className="dd-opt-label">{o.label}</span>
                  <span className="dd-opt-note">{o.note}</span>
                </button>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </section>
  );
}
