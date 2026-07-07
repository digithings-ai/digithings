"use client";

import { useState } from "react";
import { m, useReducedMotion } from "motion/react";
import { Emblem, modules } from "@digithings/web";

/**
 * Feature picker — one viewport that tours the modules: pick one from the rail
 * and the panel swaps to its emblem + copy, dressing the section in that module's
 * accent livery. Interactive display template.
 */
// The core + support modules make the tour; roadmap ones stay out of it.
const TOUR = modules.filter((mod) => mod.tier !== "roadmap").slice(0, 7);

export function FeaturePickerReference() {
  const reduced = useReducedMotion();
  const [active, setActive] = useState(TOUR[0].id);
  const current = TOUR.find((mod) => mod.id === active) ?? TOUR[0];

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
        {TOUR.map((mod) => (
          <button
            key={mod.id}
            type="button"
            role="tab"
            aria-selected={mod.id === active}
            className={`fp-tab accent-${mod.id}${mod.id === active ? " on" : ""}`}
            onClick={() => setActive(mod.id)}
          >
            <Emblem id={mod.id} size={22} />
            <span>{mod.name}</span>
          </button>
        ))}
      </div>

      <m.div
        key={reduced ? "static" : current.id}
        className="fp-panel"
        role="tabpanel"
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
        <span className="absolute right-[1rem] top-[1rem] rounded-full border border-hair px-[0.5rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
          {current.tier === "core" ? "core module" : "supporting"}
        </span>
      </m.div>
    </section>
  );
}
