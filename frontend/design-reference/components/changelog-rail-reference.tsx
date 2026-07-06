"use client";

import { useRef } from "react";
import { useReducedMotion } from "motion/react";

type Release = {
  version: string;
  date: string;
  title: string;
  entries: string[];
  tag: "feature" | "fix" | "breaking";
};

const RELEASES: Release[] = [
  {
    version: "v2.4",
    date: "2026-06-28",
    title: "Kelly-capped sizing",
    tag: "feature",
    entries: ["Position sizer honours a per-strategy Kelly cap.", "Flat-state guard on the momentum gate."],
  },
  {
    version: "v2.3",
    date: "2026-06-09",
    title: "Polars end to end",
    tag: "breaking",
    entries: ["Removed the legacy pandas resampler.", "Bar loaders now return Polars frames."],
  },
  {
    version: "v2.2",
    date: "2026-05-21",
    title: "Drawdown accounting",
    tag: "fix",
    entries: ["Fixed maxDD across session boundaries.", "Tearsheet PF matches the ledger."],
  },
  {
    version: "v2.1",
    date: "2026-05-02",
    title: "Atlas research loop",
    tag: "feature",
    entries: ["Atlas proposes directions from free data.", "Hermes routes signals to the sizer."],
  },
  {
    version: "v2.0",
    date: "2026-04-14",
    title: "Olympus sub-graphs",
    tag: "breaking",
    entries: ["Split Atlas / Hermes / Kairos into sub-graphs.", "Supervisor rewired around the split."],
  },
];

export function ChangelogRailReference() {
  const railRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();

  const nudge = (dir: 1 | -1) => {
    railRef.current?.scrollBy({ left: dir * 300, behavior: reduced ? "auto" : "smooth" });
  };

  return (
    <section className="section-block changelog-rail">
      <div className="cr-head">
        <div>
          <p className="kicker">{"// changelog rail"}</p>
          <h2 className="title">Content that scrolls sideways.</h2>
        </div>
        <div className="cr-nav" aria-hidden="true">
          <button type="button" className="cr-arrow" onClick={() => nudge(-1)} aria-label="Scroll left">
            ‹
          </button>
          <button type="button" className="cr-arrow" onClick={() => nudge(1)} aria-label="Scroll right">
            ›
          </button>
        </div>
      </div>
      <p className="section-copy">
        Changelog-class content lives on a horizontal rail: swipe it, wheel it, or use the arrows.
        Cards snap into place and the edges fade so the row reads as a strip, not a cut-off grid.
        This is also the sanctioned mobile fallback for any band too wide to stack.
      </p>

      <div className="cr-mask">
        <div ref={railRef} className="cr-track" role="list" aria-label="Release notes">
          {RELEASES.map((rel) => (
            <article key={rel.version} className="cr-card" role="listitem" tabIndex={0}>
              <div className="cr-card-head">
                <span className="cr-version">{rel.version}</span>
                <span className={`cr-tag cr-tag-${rel.tag}`}>{rel.tag}</span>
              </div>
              <p className="cr-date">{rel.date}</p>
              <h3 className="cr-title">{rel.title}</h3>
              <ul>
                {rel.entries.map((entry) => (
                  <li key={entry}>{entry}</li>
                ))}
              </ul>
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
