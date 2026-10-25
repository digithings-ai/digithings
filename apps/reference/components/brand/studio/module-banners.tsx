"use client";

import type { CSSProperties } from "react";
import { BANNERS } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

const BANNER_LIST = Object.values(BANNERS);

/**
 * The live index of every registered module wordmark banner.
 *
 * These are not copied artwork: `BANNERS` is the same registry the marketing
 * sites and terminals read, so editing a definition updates this gallery.
 */
export function ModuleBanners() {
  return (
    <section className="section-block mb-section" aria-labelledby="module-banners-title">
      <p className="kicker">{"// module banners"}</p>
      <h2 className="title" id="module-banners-title">
        Every module, already animated.
      </h2>
      <p className="section-copy">
        The 15 wordmark banners render live from{" "}
        <code>packages/hero-banner/src/definitions/index.ts</code> — the same
        definitions the sites and terminals use. Nothing is copied here, so a
        definition change reaches every surface. The <code>digivoice</code> baseline and
        review variants are intentionally excluded.
      </p>

      <div className="mb-grid">
        {BANNER_LIST.map((definition) => {
          const accent = definition.palette.accent;
          const accentStyle =
            accent?.cssVar && accent.hex
              ? ({ [accent.cssVar]: accent.hex } as CSSProperties)
              : undefined;
          return (
            <article className="mb-card" key={definition.id} style={accentStyle}>
              <div className="mb-frame">
                <HeroBanner def={definition} className="mb-canvas" />
              </div>
              <div className="mb-meta">
                <span className="mb-name">{definition.id}</span>
                <span className="mb-accent">
                  <span
                    className="mb-swatch"
                    style={{ background: accent?.hex ?? "#ECEEF0" }}
                    aria-hidden="true"
                  />
                  {accent?.hex ?? "mono"}
                </span>
              </div>
            </article>
          );
        })}
      </div>
    </section>
  );
}
