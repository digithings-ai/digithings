"use client";

import { useState } from "react";
import { m, useReducedMotion } from "motion/react";
import { modules } from "@digithings/web";

/** Reads --accent-<id> off <html> — "" during SSR, where computed styles
 *  don't exist. */
function readAccentHex(id: string): string {
  if (typeof document === "undefined") return "";
  return getComputedStyle(document.documentElement).getPropertyValue(`--accent-${id}`).trim();
}

/**
 * Livery switcher — a self-contained swatch strip demoing the per-module accent
 * colours (local state only, not the app-wide store). Shows how a livery
 * recolours an accented surface. Interactive display template.
 *
 * The module list is derived from the shared modules registry (roadmap tier
 * excluded), the same filter FeaturePickerReference and LIVERY_OPTIONS use —
 * this file used to hand-maintain its own separate 7-module array (missing
 * digismith/digiclaw/digibase, including roadmap-tier digistore) that
 * disagreed with both of those. The displayed hex value is read from the
 * live --accent-<module> custom property rather than a hardcoded literal, so
 * it can never drift from tokens.css.
 */
const LIVERIES = modules
  .filter((mod) => mod.tier !== "roadmap")
  .map((mod) => ({ id: mod.id, label: mod.name }));

export function LiverySwitcher() {
  const [active, setActive] = useState<(typeof LIVERIES)[number]["id"]>("digiquant");
  const reduceMotion = useReducedMotion();
  const activeLivery = LIVERIES.find((l) => l.id === active) ?? LIVERIES[0];

  // Adjust during render when `active` changes, rather than in an effect
  // (react-hooks/set-state-in-effect) — the same "resetting state when a
  // prop changes" idiom used elsewhere in this codebase (e.g. site-nav.tsx's
  // pathname handler, useEmbedGate's host handler).
  const [activeHexFor, setActiveHexFor] = useState(() => ({
    id: active,
    hex: readAccentHex(active),
  }));
  if (activeHexFor.id !== active) {
    setActiveHexFor({ id: active, hex: readAccentHex(active) });
  }
  const activeHex = activeHexFor.hex;

  return (
    <section className={`section-block livery-switcher accent-${active}`}>
      <p className="kicker">{"// livery"}</p>
      <h2 className="title">One instrumentation color per module. Pick one.</h2>
      <p className="section-copy">
        Law 02: color is quarantined to data and identity, never decoration. Every module
        gets exactly one accent — switching here previews the same components under a
        different livery, live.
      </p>

      <div className="mt-[1.2rem] flex flex-wrap gap-2">
        {LIVERIES.map((livery) => (
          <button
            key={livery.id}
            type="button"
            className={`livery-chip${livery.id === active ? " on" : ""}`}
            style={{ ["--chip" as string]: `var(--accent-${livery.id})` }}
            onClick={() => setActive(livery.id)}
            aria-pressed={livery.id === active}
          >
            <span className="livery-dot" />
            {livery.label}
          </button>
        ))}
      </div>

      <div className="mt-[1.2rem]">
        <m.div
          key={active}
          className="flex flex-wrap items-center gap-y-[0.9rem] gap-x-[1.4rem] rounded-[12px] border border-hair bg-surface p-[1.2rem]"
          initial={reduceMotion ? false : { opacity: 0, y: 8 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.28, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="font-mono text-[0.68rem] uppercase tracking-[0.08em] text-ink-mute">{activeLivery.label} / accent</span>
          <span className="font-mono text-[0.9rem] text-accent">{activeHex}</span>
          <div className="flex w-full items-center gap-[0.6rem]">
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
