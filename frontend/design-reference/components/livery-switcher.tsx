"use client";

import { useState } from "react";
import { m, useReducedMotion } from "motion/react";

const LIVERIES = [
  { id: "digigraph", label: "DigiGraph", hex: "#e5b765" },
  { id: "digiquant", label: "DigiQuant", hex: "#3dd6c4" },
  { id: "digisearch", label: "DigiSearch", hex: "#5aa3c4" },
  { id: "digichat", label: "DigiChat", hex: "#e2708a" },
  { id: "digikey", label: "DigiKey", hex: "#d97a5a" },
  { id: "digivault", label: "DigiVault", hex: "#9d8fc9" },
  { id: "digistore", label: "DigiStore", hex: "#7b7fc7" },
  { id: "atlas", label: "Atlas", hex: "#6fbf94" },
] as const;

export function LiverySwitcher() {
  const [active, setActive] = useState<(typeof LIVERIES)[number]["id"]>("digiquant");
  const reduceMotion = useReducedMotion();
  const activeLivery = LIVERIES.find((l) => l.id === active) ?? LIVERIES[0];

  return (
    <section className={`section-block livery-switcher accent-${active}`}>
      <p className="kicker">{"// livery"}</p>
      <h2 className="title">One instrumentation color per module. Pick one.</h2>
      <p className="section-copy">
        Law 02: color is quarantined to data and identity, never decoration. Every module
        gets exactly one accent — switching here previews the same components under a
        different livery, live.
      </p>

      <div className="livery-grid">
        {LIVERIES.map((livery) => (
          <button
            key={livery.id}
            type="button"
            className={`livery-chip${livery.id === active ? " on" : ""}`}
            style={{ ["--chip" as string]: livery.hex }}
            onClick={() => setActive(livery.id)}
            aria-pressed={livery.id === active}
          >
            <span className="livery-dot" />
            {livery.label}
          </button>
        ))}
      </div>

      <div className="livery-preview">
        <m.div
          key={active}
          className="livery-preview-card"
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="livery-preview-label">{activeLivery.label} / accent</span>
          <span className="livery-preview-hex">{activeLivery.hex}</span>
          <div className="livery-preview-row">
            <button type="button" className="btn-primary">
              Primary action
            </button>
            <button type="button" className="btn-ghost">
              Secondary
            </button>
            <span className="livery-preview-pulse" aria-hidden="true" />
          </div>
        </m.div>
      </div>
    </section>
  );
}
