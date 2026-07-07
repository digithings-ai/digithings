"use client";

import { useState } from "react";

/**
 * Skeleton loading states — placeholder shapes with a shimmer sweep that stand
 * in until content arrives, then swap 1:1 to the real layout. The shimmer is a
 * translating gradient over ink-tinted shapes (no accent needed — reads under
 * the monochrome default); money colors only appear in the loaded state where
 * they mean something. A toggle replays the load. Reduced motion drops the
 * shimmer and shows a static placeholder.
 */
const METRICS = [
  { k: "CAGR", v: "+44.9%", tone: "up" },
  { k: "SHARPE", v: "2.31" },
  { k: "MAX DD", v: "−18.4%", tone: "down" },
];

export function SkeletonReference() {
  const [loading, setLoading] = useState(true);

  return (
    <section className="section-block">
      <p className="kicker">{"// loading states"}</p>
      <h2 className="title">Skeletons, then content.</h2>
      <p className="section-copy">
        Placeholder shapes with a shimmer hold the layout until data lands, then swap to the real
        thing with no reflow. The shimmer rides ink tints so it works in any theme; money colors
        only show once there&apos;s a number to color. Replay the load below.
      </p>

      <div className="mt-[1.2rem]">
        <button
          type="button"
          className={`sk-toggle${loading ? " on" : ""}`}
          role="switch"
          aria-checked={loading}
          onClick={() => setLoading((v) => !v)}
        >
          <span className="sk-toggle-track" aria-hidden="true">
            <span className="sk-toggle-knob" />
          </span>
          {loading ? "loading" : "loaded"}
        </button>
      </div>

      <div className="mt-[1.1rem] flex flex-col gap-[1rem]" aria-busy={loading}>
        {/* profile / strategy card */}
        <article className="flex items-center gap-[0.9rem] rounded-[12px] border border-hair bg-surface px-[1.1rem] py-[1rem]">
          {loading ? (
            <>
              <span className="sk sk-circle" />
              <div className="flex min-w-0 flex-1 flex-col gap-[0.5rem]">
                <span className="sk sk-line" style={{ width: "55%" }} />
                <span className="sk sk-line" style={{ width: "38%" }} />
              </div>
              <span className="sk sk-btn" />
            </>
          ) : (
            <>
              <span
                className="grid size-10 shrink-0 place-items-center rounded-full bg-accent/16 font-mono text-[1rem] text-accent"
                aria-hidden="true"
              >
                t
              </span>
              <div className="flex min-w-0 flex-1 flex-col gap-[0.5rem]">
                <p className="m-0 font-mono text-[0.9rem] text-ink">trend_xsec</p>
                <p className="m-0 font-mono text-[0.72rem] text-ink-mute">cross-sectional momentum</p>
              </div>
              <button type="button" className="btn-ghost">
                View tearsheet
              </button>
            </>
          )}
        </article>

        {/* metric tiles */}
        <div className="grid grid-cols-3 gap-[0.7rem] max-[560px]:grid-cols-1">
          {METRICS.map((m, i) => (
            <div
              className="flex min-h-[4.4rem] flex-col gap-[0.5rem] rounded-[10px] border border-hair bg-surface px-[1rem] py-[0.9rem]"
              key={m.k}
            >
              {loading ? (
                <>
                  <span className="sk sk-line sk-line--sm" style={{ width: `${40 + i * 8}%` }} />
                  <span className="sk sk-block" />
                </>
              ) : (
                <>
                  <span className="font-mono text-[0.54rem] uppercase tracking-[0.1em] text-ink-mute">
                    {m.k}
                  </span>
                  <span
                    className={`font-mono text-[1.3rem] tabular-nums ${
                      m.tone === "up" ? "text-up" : m.tone === "down" ? "text-down" : "text-ink"
                    }`}
                  >
                    {m.v}
                  </span>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
