"use client";

import { useEffect, useRef, useState } from "react";
import { useReducedMotion } from "motion/react";

/**
 * Changelog rail — a horizontal scroll strip of release cards. Swipe, wheel, or
 * use the arrow buttons to move; cards snap into place and the edges fade so the
 * row reads as a continuous strip rather than a cut-off grid. Tags wear the up /
 * down colours by kind. Doubles as the sanctioned mobile fallback for any band
 * too wide to stack. Interactive display template.
 */
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
    title: "research loop",
    tag: "feature",
    entries: ["research proposes directions from free data.", "portfolio routes signals to the sizer."],
  },
  {
    version: "v2.0",
    date: "2026-04-14",
    title: "dashboard sub-graphs",
    tag: "breaking",
    entries: ["Split research / portfolio / execution into sub-graphs.", "Supervisor rewired around the split."],
  },
];

export function ChangelogRailReference() {
  const railRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  // Boundary state for the arrow buttons — without it, clicking '›' past the
  // last card (or '‹' before the first) does nothing with no visible cue,
  // which reads as the control being broken rather than the strip being
  // exhausted.
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);
  // .cr-track's own padding (2.2rem each side, for the edge-fade mask)
  // combined with scroll-snap-align: start on the FIRST .cr-card means the
  // browser's natural resting scrollLeft is NOT 0 — confirmed live:
  // scrollTo({left: 0}) and even a negative value both settle back to
  // ~35px. This is a start-only effect, not a symmetric one: scroll-snap
  // has no "align: end" card to pull the far side inward, so the true
  // maximum IS the theoretical scrollWidth - clientWidth (confirmed live:
  // scrollTo({left: 999999}) settles within a sub-pixel of that value, not
  // ~35px short of it as an earlier version of this comment incorrectly
  // claimed). Comparing the start against a hardcoded 0 would leave the
  // left arrow permanently enabled with nowhere further to scroll, so the
  // true minimum is captured once on mount (before any user scrolling)
  // instead of assumed.
  const minScrollLeftRef = useRef<number | null>(null);

  const updateBoundaries = () => {
    const el = railRef.current;
    if (!el) return;
    if (minScrollLeftRef.current === null) minScrollLeftRef.current = el.scrollLeft;
    const min = minScrollLeftRef.current;
    const max = el.scrollWidth - el.clientWidth;
    // Sub-pixel scroll widths make an exact equality check flaky; 1px slack.
    setAtStart(el.scrollLeft <= min + 1);
    setAtEnd(el.scrollLeft >= max - 1);
  };

  useEffect(() => {
    updateBoundaries();
    const el = railRef.current;
    if (!el) return;
    el.addEventListener("scroll", updateBoundaries, { passive: true });
    // A resize (viewport, or a responsive breakpoint flip) changes
    // clientWidth/scrollWidth without firing a scroll event, which would
    // otherwise leave atStart/atEnd — and the arrows' disabled state —
    // stale until the user happens to scroll again.
    const observer = new ResizeObserver(updateBoundaries);
    observer.observe(el);
    return () => {
      el.removeEventListener("scroll", updateBoundaries);
      observer.disconnect();
    };
  }, []);

  const nudge = (dir: 1 | -1) => {
    railRef.current?.scrollBy({ left: dir * 300, behavior: reduced ? "auto" : "smooth" });
  };

  return (
    <section className="section-block changelog-rail">
      <div className="flex items-end justify-between gap-4">
        <div>
          <p className="kicker">{"// changelog rail"}</p>
          <h2 className="title">Content that scrolls sideways.</h2>
        </div>
        <div className="flex gap-[0.4rem]">
          <button
            type="button"
            className="cr-arrow"
            onClick={() => nudge(-1)}
            aria-label="Scroll left"
            disabled={atStart}
          >
            ‹
          </button>
          <button
            type="button"
            className="cr-arrow"
            onClick={() => nudge(1)}
            aria-label="Scroll right"
            disabled={atEnd}
          >
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
        <div
          ref={railRef}
          className="cr-track"
          role="list"
          aria-label="Release notes, scrollable horizontally"
          tabIndex={0}
        >
          {RELEASES.map((rel) => (
            <article key={rel.version} className="cr-card" role="listitem" tabIndex={0}>
              <div className="flex items-center justify-between">
                <span className="font-mono text-[0.95rem] text-ink">{rel.version}</span>
                <span className={`cr-tag cr-tag-${rel.tag}`}>{rel.tag}</span>
              </div>
              <p className="mt-[0.5rem] font-mono text-[0.62rem] tracking-[0.06em] text-ink-mute">{rel.date}</p>
              <h3 className="mt-[0.15rem] text-[1.05rem] text-ink">{rel.title}</h3>
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
