"use client";

import { useEffect, useRef, useState } from "react";
import { BANNERS } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";
import type { BannerDefinition } from "@digithings/hero-banner";

/**
 * A module's hero banner (@digithings/hero-banner), held blank until it first
 * scrolls into view, then left running: LOADING plays once, LIVE stays on.
 * Reduced motion is the engine's job — it paints the settled mark and never
 * starts a timer, so arming changes nothing there.
 *
 * `inView={false}` arms at mount: the top-bar mark is always on screen.
 */
export function ScrollBanner({
  def,
  live = true,
  inView = true,
  className,
}: {
  def: BannerDefinition;
  live?: boolean;
  inView?: boolean;
  className?: string;
}) {
  const ref = useRef<HTMLSpanElement | null>(null);
  const [armed, setArmed] = useState(!inView);

  useEffect(() => {
    const el = ref.current;
    if (armed || !el) return;
    if (typeof IntersectionObserver !== "function") {
      // No observer to wait on: arm on the next frame, not in the effect body.
      const raf = requestAnimationFrame(() => setArmed(true));
      return () => cancelAnimationFrame(raf);
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setArmed(true);
          io.disconnect();
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [armed]);

  return (
    <span ref={ref} className={className} style={{ display: "block" }}>
      <HeroBanner def={def} live={live} armed={armed} />
    </span>
  );
}

/** The registered banner for a module id, if the family has one yet. */
export function bannerFor(id: string): BannerDefinition | undefined {
  return (BANNERS as Record<string, BannerDefinition | undefined>)[id];
}
