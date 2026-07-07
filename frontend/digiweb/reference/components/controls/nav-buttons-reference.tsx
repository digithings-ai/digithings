"use client";

import { useState } from "react";

const SEGMENTS = ["1D", "1W", "1M", "1Y", "All"];
const PAGES = 5;

export function NavButtonsReference() {
  const [seg, setSeg] = useState("1M");
  const [page, setPage] = useState(1);

  return (
    <section className="section-block">
      <p className="kicker">{"// navigation buttons"}</p>
      <h2 className="title">Move between things.</h2>
      <p className="section-copy">
        The wayfinding controls: a segmented range switch (the selected cell wears an accent-weak
        wash), a prev/next pager with a disabled edge state, and borderless icon buttons. Pills for
        chrome, hairline for structure — one loud state per group.
      </p>

      <div className="ctl-nav-row">
        <p className="ctl-sub">segmented</p>
        <div className="nb-segmented" role="tablist" aria-label="Range">
          {SEGMENTS.map((s) => (
            <button
              key={s}
              type="button"
              role="tab"
              aria-selected={s === seg}
              className={`nb-seg${s === seg ? " on" : ""}`}
              onClick={() => setSeg(s)}
            >
              {s}
            </button>
          ))}
        </div>
      </div>

      <div className="ctl-nav-row">
        <p className="ctl-sub">pager</p>
        <div className="nb-pager">
          <button
            type="button"
            className="nb-page-edge"
            disabled={page === 1}
            onClick={() => setPage((p) => Math.max(1, p - 1))}
          >
            ‹ prev
          </button>
          {Array.from({ length: PAGES }, (_, i) => i + 1).map((n) => (
            <button
              key={n}
              type="button"
              className={`nb-page${n === page ? " on" : ""}`}
              aria-current={n === page ? "page" : undefined}
              onClick={() => setPage(n)}
            >
              {n}
            </button>
          ))}
          <button
            type="button"
            className="nb-page-edge"
            disabled={page === PAGES}
            onClick={() => setPage((p) => Math.min(PAGES, p + 1))}
          >
            next ›
          </button>
        </div>
      </div>

      <div className="ctl-nav-row">
        <p className="ctl-sub">icon buttons</p>
        <div className="nb-icons">
          {[
            { k: "back", d: "M15 5l-7 7 7 7" },
            { k: "fwd", d: "M9 5l7 7-7 7" },
            { k: "refresh", d: "M4 12a8 8 0 1 1 2.3 5.6M4 20v-3.4h3.4" },
            { k: "more", d: "M12 6h.01M12 12h.01M12 18h.01" },
          ].map((b) => (
            <button key={b.k} type="button" className="nb-icon" aria-label={b.k}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d={b.d} />
              </svg>
            </button>
          ))}
        </div>
      </div>
    </section>
  );
}
