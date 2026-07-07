"use client";

import { useSyncExternalStore } from "react";
import {
  applyLivery,
  getLiverySnapshot,
  getLiveryServerSnapshot,
  LIVERY_OPTIONS,
  subscribeLivery,
} from "@/components/livery-store";

/**
 * Theme gallery — the livery swatches, wired to the same store as the nav's
 * livery selector, so choosing one dresses the whole app and persists across
 * navigation. Interactive display template.
 */
export function ThemeGallery() {
  // Shared with the nav's livery selector — selecting here dresses the whole
  // app and persists across navigation (see components/livery-store.ts).
  const active = useSyncExternalStore(subscribeLivery, getLiverySnapshot, getLiveryServerSnapshot);

  return (
    <section className="section-block theme-gallery">
      <p className="kicker">{"// theme"}</p>
      <h2 className="title">Dress the whole reference.</h2>
      <p className="section-copy">
        Pick a livery and the entire app re-dresses — nav, links, charts, every accent — and the
        choice sticks as you move between pages (it&apos;s mirrored in the top-bar selector).
        Monochrome is the umbrella treatment (accent collapses to ink). Light and dark live in the
        toggle beside it; the two compose.
      </p>

      <div className="tg-grid" role="radiogroup" aria-label="Page livery">
        {LIVERY_OPTIONS.map((o) => (
          <button
            key={o.id}
            type="button"
            role="radio"
            aria-checked={o.id === active}
            className={`tg-swatch${o.id === active ? " on" : ""}`}
            style={{ ["--tg" as string]: o.hex }}
            onClick={() => applyLivery(o.id)}
          >
            <span className="tg-chip" aria-hidden="true" />
            <span className="tg-label">{o.label}</span>
          </button>
        ))}
      </div>
    </section>
  );
}
