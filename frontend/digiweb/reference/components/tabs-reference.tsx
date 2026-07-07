"use client";

import { useCallback, useLayoutEffect, useRef, useState } from "react";
import { m, useReducedMotion } from "motion/react";

type Tab = { id: string; label: string };

/**
 * Reusable tab strip with a sliding active indicator. The indicator is a single
 * absolutely-positioned element whose transform/width are measured from the
 * active tab and written straight to a ref, so the slide is a CSS transition —
 * no `layoutId` (the app's LazyMotion runs `domAnimation`, which omits layout
 * animations) and no per-frame React state.
 */
function TabStrip({
  tabs,
  active,
  onChange,
  variant,
  label,
}: {
  tabs: Tab[];
  active: number;
  onChange: (i: number) => void;
  variant: "underline" | "pill";
  label: string;
}) {
  const listRef = useRef<HTMLDivElement>(null);
  const inkRef = useRef<HTMLSpanElement>(null);
  const mounted = useRef(false);
  const reduced = useReducedMotion();

  const position = useCallback(
    (animate: boolean) => {
      const list = listRef.current;
      const ink = inkRef.current;
      if (!list || !ink) return;
      const el = list.querySelectorAll<HTMLButtonElement>('[role="tab"]')[active];
      if (!el) return;
      ink.style.transition = animate ? "" : "none";
      ink.style.transform = `translateX(${el.offsetLeft}px)`;
      ink.style.width = `${el.offsetWidth}px`;
      if (!animate) {
        // flush the jump before restoring the transition so it never animates
        void ink.offsetWidth;
        ink.style.transition = "";
      }
    },
    [active],
  );

  useLayoutEffect(() => {
    position(mounted.current && !reduced);
    mounted.current = true;
  }, [position, reduced]);

  useLayoutEffect(() => {
    const onResize = () => position(false);
    window.addEventListener("resize", onResize);
    return () => window.removeEventListener("resize", onResize);
  }, [position]);

  const onKeyDown = (e: React.KeyboardEvent) => {
    let next = active;
    if (e.key === "ArrowRight") next = (active + 1) % tabs.length;
    else if (e.key === "ArrowLeft") next = (active - 1 + tabs.length) % tabs.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = tabs.length - 1;
    else return;
    e.preventDefault();
    onChange(next);
    listRef.current?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[next]?.focus();
  };

  const base = label.replace(/\s+/g, "-");

  return (
    <div
      ref={listRef}
      className={`tab-strip ${variant}`}
      role="tablist"
      aria-label={label}
      onKeyDown={onKeyDown}
    >
      <span ref={inkRef} className={`tab-ink ${variant}`} aria-hidden="true" />
      {tabs.map((t, i) => (
        <button
          key={t.id}
          type="button"
          role="tab"
          id={`${base}-tab-${t.id}`}
          aria-selected={i === active}
          aria-controls={`${base}-panel-${t.id}`}
          tabIndex={i === active ? 0 : -1}
          className="tab-btn"
          onClick={() => onChange(i)}
        >
          {t.label}
        </button>
      ))}
    </div>
  );
}

const VIEWS: Tab[] = [
  { id: "overview", label: "Overview" },
  { id: "positions", label: "Positions" },
  { id: "orders", label: "Orders" },
  { id: "logs", label: "Logs" },
];

const POSITIONS = [
  { sym: "BTC-PERP", qty: "+1.20", pnl: 4820, up: true },
  { sym: "ETH-PERP", qty: "+8.00", pnl: 1290, up: true },
  { sym: "SOL-PERP", qty: "−140", pnl: -640, up: false },
];

const ORDERS = [
  { sym: "BTC-PERP", side: "buy", px: "63,410", qty: "0.40" },
  { sym: "ETH-PERP", side: "sell", px: "3,088", qty: "4.00" },
  { sym: "SOL-PERP", side: "buy", px: "142.6", qty: "60" },
];

const LOGS = [
  "12:04:31  fill  BTC-PERP  +0.40 @ 63,410",
  "12:04:29  ack   order 8f2c accepted",
  "12:04:27  risk  gross exposure 0.62× limit",
  "12:03:58  sig   trend_xsec → long BTC",
];

const MODES: Tab[] = [
  { id: "backtest", label: "backtest" },
  { id: "paper", label: "paper" },
  { id: "live", label: "live" },
];

const MODE_NOTE = [
  "Replays historical bars — no venue connection.",
  "Live market data, simulated fills, zero capital at risk.",
  "Routes to the broker. Gated behind human approval.",
];

export function TabsReference() {
  const [view, setView] = useState(0);
  const [mode, setMode] = useState(1);
  const reduced = useReducedMotion();

  const panelMotion = reduced
    ? {}
    : { initial: { opacity: 0, y: 6 }, animate: { opacity: 1, y: 0 }, transition: { duration: 0.22 } };

  const activeId = VIEWS[view].id;

  return (
    <section className="section-block">
      <p className="kicker">{"// tabs"}</p>
      <h2 className="title">Panels, with a slider.</h2>
      <p className="section-copy">
        A tab strip whose active indicator slides between labels — measured from the live tab
        geometry and animated with a CSS transition, so it survives a resize and honours
        reduced-motion. Arrow keys move between tabs; the panel below crossfades in. Two dresses:
        an underline for content regions, a pill for a compact mode switch.
      </p>

      <div className="tabs-demo">
        <TabStrip
          tabs={VIEWS}
          active={view}
          onChange={setView}
          variant="underline"
          label="Account view"
        />

        <div
          className="tab-panel"
          role="tabpanel"
          id={`Account-view-panel-${activeId}`}
          aria-labelledby={`Account-view-tab-${activeId}`}
        >
          <m.div key={view} {...panelMotion}>
            {activeId === "overview" && (
              <div className="tab-overview">
                {[
                  { k: "Equity", v: "$1.284M" },
                  { k: "Day P&L", v: "+$5.47K", up: true },
                  { k: "Sharpe", v: "2.31" },
                  { k: "Exposure", v: "0.62×" },
                ].map((s) => (
                  <div key={s.k} className="tab-stat">
                    <span className="tab-stat-k">{s.k}</span>
                    <span className={`tab-stat-v${s.up ? " up" : ""}`}>{s.v}</span>
                  </div>
                ))}
              </div>
            )}

            {activeId === "positions" && (
              <div className="tab-rows">
                {POSITIONS.map((p) => (
                  <div key={p.sym} className="tab-row">
                    <span className="tab-sym">{p.sym}</span>
                    <span className="tab-qty">{p.qty}</span>
                    <span className={`tab-pnl ${p.up ? "up" : "down"}`}>
                      {p.up ? "+" : "−"}${Math.abs(p.pnl).toLocaleString()}
                    </span>
                  </div>
                ))}
              </div>
            )}

            {activeId === "orders" && (
              <div className="tab-rows">
                {ORDERS.map((o) => (
                  <div key={o.sym} className="tab-row">
                    <span className={`tab-side ${o.side}`}>{o.side}</span>
                    <span className="tab-sym">{o.sym}</span>
                    <span className="tab-qty">{o.qty}</span>
                    <span className="tab-px">{o.px}</span>
                  </div>
                ))}
              </div>
            )}

            {activeId === "logs" && (
              <div className="tab-logs">
                {LOGS.map((l) => (
                  <p key={l} className="tab-log">
                    {l}
                  </p>
                ))}
              </div>
            )}
          </m.div>
        </div>
      </div>

      <div className="tabs-demo tabs-demo--pill">
        <TabStrip
          tabs={MODES}
          active={mode}
          onChange={setMode}
          variant="pill"
          label="Execution mode"
        />
        <p className="tab-mode-note">{MODE_NOTE[mode]}</p>
      </div>
    </section>
  );
}
