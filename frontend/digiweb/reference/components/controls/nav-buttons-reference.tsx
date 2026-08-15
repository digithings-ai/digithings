"use client";

import { useState } from "react";

import { IconButton, Pager, PagerPage, SegmentedControl } from "@digithings/web";

/**
 * Navigation buttons — the wayfinding controls: a segmented range switch (the
 * selected cell wears an accent-weak wash), a prev/next pager with a disabled
 * edge state and a current-page marker, and borderless icon buttons. Pills for
 * chrome, hairline for structure — one loud state per group. Static interactive
 * display template. Consumes the shared <SegmentedControl/>, <Pager/> and
 * <IconButton/> primitives from @digithings/web (selection rides aria-pressed /
 * aria-current — not the tablist this specimen once misused).
 */
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

      <div className="mt-[1.4rem]">
        <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
          segmented
        </p>
        <SegmentedControl options={SEGMENTS} value={seg} onChange={setSeg} aria-label="Range" />
      </div>

      <div className="mt-[1.4rem]">
        <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
          pager
        </p>
        <Pager
          prevDisabled={page === 1}
          nextDisabled={page === PAGES}
          onPrev={() => setPage((p) => Math.max(1, p - 1))}
          onNext={() => setPage((p) => Math.min(PAGES, p + 1))}
        >
          {Array.from({ length: PAGES }, (_, i) => i + 1).map((n) => (
            <PagerPage key={n} current={n === page} onClick={() => setPage(n)}>
              {n}
            </PagerPage>
          ))}
        </Pager>
      </div>

      <div className="mt-[1.4rem]">
        <p className="mb-[0.5rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
          icon buttons
        </p>
        <div className="inline-flex gap-[0.3rem]">
          {[
            { k: "back", d: "M15 5l-7 7 7 7" },
            { k: "fwd", d: "M9 5l7 7-7 7" },
            { k: "refresh", d: "M4 12a8 8 0 1 1 2.3 5.6M4 20v-3.4h3.4" },
            { k: "more", d: "M12 6h.01M12 12h.01M12 18h.01" },
          ].map((b) => (
            <IconButton key={b.k} aria-label={b.k}>
              <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                <path d={b.d} />
              </svg>
            </IconButton>
          ))}
        </div>
      </div>
    </section>
  );
}
