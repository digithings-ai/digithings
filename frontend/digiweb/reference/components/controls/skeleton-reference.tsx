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

      <div className="sk-toolbar">
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

      <div className="sk-demo" aria-busy={loading}>
        {/* profile / strategy card */}
        <article className="sk-card">
          {loading ? (
            <>
              <span className="sk sk-circle" />
              <div className="sk-card-body">
                <span className="sk sk-line" style={{ width: "55%" }} />
                <span className="sk sk-line" style={{ width: "38%" }} />
              </div>
              <span className="sk sk-btn" />
            </>
          ) : (
            <>
              <span className="sk-avatar" aria-hidden="true">
                t
              </span>
              <div className="sk-card-body">
                <p className="sk-name">trend_xsec</p>
                <p className="sk-role">cross-sectional momentum</p>
              </div>
              <button type="button" className="btn-ghost">
                View tearsheet
              </button>
            </>
          )}
        </article>

        {/* metric tiles */}
        <div className="sk-tiles">
          {METRICS.map((m, i) => (
            <div className="sk-tile" key={m.k}>
              {loading ? (
                <>
                  <span className="sk sk-line sk-line--sm" style={{ width: `${40 + i * 8}%` }} />
                  <span className="sk sk-block" />
                </>
              ) : (
                <>
                  <span className="sk-tile-k">{m.k}</span>
                  <span className={`sk-tile-v${m.tone ? ` ${m.tone}` : ""}`}>{m.v}</span>
                </>
              )}
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
