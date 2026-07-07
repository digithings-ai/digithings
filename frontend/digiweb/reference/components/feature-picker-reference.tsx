"use client";

import { useState } from "react";
import { m, useReducedMotion } from "motion/react";
import { Emblem, modules } from "@digithings/web";

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
        <div className="fp-panel-body">
          <p className="fp-panel-tier">{current.tier}</p>
          <h3 className="fp-panel-name">{current.name}</h3>
          <p className="fp-panel-role">{current.role}</p>
          <p className="fp-panel-tagline">{current.tagline}</p>
        </div>
        <span className="fp-panel-tag">{current.tier === "core" ? "core module" : "supporting"}</span>
      </m.div>
    </section>
  );
}
