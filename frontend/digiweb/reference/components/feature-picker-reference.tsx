"use client";

import { useRef, useState } from "react";
import { m, useReducedMotion } from "motion/react";
import { Emblem, modules } from "@digithings/web";

/**
 * Feature picker — one viewport that tours the modules: pick one from the rail
 * and the panel swaps to its emblem + copy, dressing the section in that module's
 * accent livery. Interactive display template.
 */
// The core + support modules make the tour; roadmap ones stay out of it. Was
// `.slice(0, 7)` — an arbitrary truncation that silently dropped digibase and
// digivault and made this the third "which modules get a color" list on this
// page to disagree with the other two (LIVERY_OPTIONS, LiverySwitcher's own
// list) and with tokens.css's real registry. All three now share this exact
// filter, applied directly to the same modules registry.
const TOUR = modules.filter((mod) => mod.tier !== "roadmap");

export function FeaturePickerReference() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(TOUR[0].id);
  const current = TOUR.find((mod) => mod.id === active) ?? TOUR[0];
  const tabRefs = useRef<Array<HTMLButtonElement | null>>([]);

  // WAI-ARIA APG tabs pattern, "automatic activation": Left/Right (and
  // Home/End) move focus AND select, wrapping around at either end. Roles
  // and aria-selected already matched this pattern; only the roving
  // tabindex + key handling were missing, so screen-reader users hearing
  // "tab, digigraph, selected" had no way to move between tabs except
  // Tab/Shift+Tab through every button in document order.
  const onTabKeyDown = (e: React.KeyboardEvent<HTMLButtonElement>, index: number) => {
    let next: number | null = null;
    if (e.key === "ArrowRight") next = (index + 1) % TOUR.length;
    else if (e.key === "ArrowLeft") next = (index - 1 + TOUR.length) % TOUR.length;
    else if (e.key === "Home") next = 0;
    else if (e.key === "End") next = TOUR.length - 1;
    if (next === null) return;
    e.preventDefault();
    setActive(TOUR[next].id);
    tabRefs.current[next]?.focus();
  };

  return (
    <section className={`section-block feature-picker accent-${current.id}`}>
      <p className="kicker">{"// feature picker"}</p>
      <h2 className="title">One viewport, every module.</h2>
      <p className="section-copy">
        Graphite&apos;s icon-tab strip: instead of pinning a long scroll, a row of marks switches
        the featured surface in place. Each tab is a module emblem; picking one re-dresses the
        panel in that module&apos;s livery. On mobile the strip scrolls horizontally.
      </p>

      <div className="fp-tabs" role="tablist" aria-label="Modules">
        {TOUR.map((mod, i) => (
          <button
            key={mod.id}
            id={`fp-tab-${mod.id}`}
            ref={(el) => {
              tabRefs.current[i] = el;
            }}
            type="button"
            role="tab"
            aria-selected={mod.id === active}
            aria-controls="fp-panel"
            tabIndex={mod.id === active ? 0 : -1}
            className={`fp-tab accent-${mod.id}${mod.id === active ? " on" : ""}`}
            onClick={() => setActive(mod.id)}
            onKeyDown={(e) => onTabKeyDown(e, i)}
          >
            <Emblem id={mod.id} size={22} />
            <span>{mod.name}</span>
          </button>
        ))}
      </div>

      <m.div
        key={reduced ? "static" : current.id}
        id="fp-panel"
        className="fp-panel"
        role="tabpanel"
        aria-labelledby={`fp-tab-${current.id}`}
        initial={reduced ? false : { opacity: 0, y: 10 }}
        animate={{ opacity: 1, y: 0 }}
        transition={{ duration: 0.3, ease: [0.22, 1, 0.36, 1] }}
      >
        <div className="fp-panel-mark" aria-hidden="true">
          <Emblem id={current.id} size={40} />
        </div>
        <div className="relative">
          <p className="font-mono text-[0.6rem] uppercase tracking-[0.12em] text-accent">{current.tier}</p>
          <h3 className="mt-[0.3rem] font-mono text-[1.2rem] text-ink">{current.name}</h3>
          <p className="mt-[0.3rem] text-[0.92rem] text-ink">{current.role}</p>
          <p className="mt-[0.2rem] text-[0.85rem] text-ink-soft">{current.tagline}</p>
        </div>
        <span className="absolute right-[1rem] top-[1rem] rounded-none border border-hair px-[0.5rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
          {current.tier === "core" ? "core module" : "supporting"}
        </span>
      </m.div>
    </section>
  );
}
