"use client";

import { BANNERS } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/**
 * The home-page banner. A client component so the definition — which carries
 * animation functions — never crosses the server boundary; BANNERS is imported
 * here, inside the client graph.
 */
export function HomeBanner() {
  return <HeroBanner def={BANNERS.digithings} className="dw-banner-canvas" />;
}
