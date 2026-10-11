"use client";

import { BANNERS } from "../../../../packages/hero-banner/src/definitions";
import type { BannerDefinition } from "../../../../packages/hero-banner/src/types";
import { HeroBanner } from "../../../../packages/hero-banner/src/web";

/** A module's own hero banner, small. Client-side because a banner definition
 *  carries its animation functions, which cannot cross from a server component. */
export function ModuleBanner({ name, className }: { name: string; className?: string }) {
  const def = (BANNERS as Record<string, BannerDefinition>)[name];
  return def ? <HeroBanner def={def} className={className} /> : null;
}
