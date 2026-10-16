"use client";
/**
 * ScrollyFeatures — shared pinned-section + progress-rail primitive (Graphite
 * pattern). Desktop: a `position: sticky` pin whose active slide advances with
 * scroll. Small viewport / reduced-motion: consumers render every slide in flow
 * (see `stepper`). Generalizes the scroll→slide logic that `ScrollyGraph`
 * (components/graph.tsx) and digiquant-web's `PipelineScene` hand-roll.
 *
 * The hook owns state only; markup + CSS stay with the consumer (the
 * `scrolly-*` classes in styles/web-theme.css are the reference skin). Pure math
 * lives in ./scrolly-core (unit-tested).
 *
 * Usage:
 *   const trackRef = useRef<HTMLDivElement>(null);
 *   const { activeIndex, stepper } = useScrollyFeatures(trackRef, { slideCount: slides.length });
 *   if (stepper) return <FlowStepper slides={slides} />;   // all slides, no pin
 *   return (
 *     <div ref={trackRef} className="scrolly-track"
 *          style={{ height: `${scrollyTrackHeightVh(slides.length)}vh` }}>
 *       <div className="scrolly-pin">…active slide…<ScrollyRail count={slides.length} activeIndex={activeIndex} /></div>
 *     </div>
 *   );
 *
 * Docs note (EVOLUTION.md §9): **max one pinned section per page.**
 */
import { useEffect, useRef, useState, type RefObject } from "react";
import { useScroll, useMotionValueEvent } from "motion/react";
import { progressToIndex, STEPPER_MEDIA_QUERY } from "./scrolly-core";

export { progressToIndex, scrollyTrackHeightVh, STEPPER_MEDIA_QUERY } from "./scrolly-core";

export interface ScrollyFeatures {
  /** Scroll-driven active slide index, clamped to the slide range. */
  activeIndex: number;
  /** True on small viewport OR reduced-motion — render all slides in flow, unpinned. */
  stepper: boolean;
}

export interface UseScrollyFeaturesOptions {
  slideCount: number;
  /** Fired once per active-slide change (not per scroll frame). */
  onSlideChange?: (index: number) => void;
}

export function useScrollyFeatures(
  trackRef: RefObject<HTMLElement | null>,
  { slideCount, onSlideChange }: UseScrollyFeaturesOptions,
): ScrollyFeatures {
  const [activeIndex, setActiveIndex] = useState(0);
  const [stepper, setStepper] = useState(false);
  const prevIndex = useRef(0);

  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia(STEPPER_MEDIA_QUERY);
    const apply = () => setStepper(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);

  const { scrollYProgress } = useScroll({ target: trackRef, offset: ["start start", "end end"] });
  useMotionValueEvent(scrollYProgress, "change", (p) => {
    const i = progressToIndex(p, slideCount);
    if (i !== prevIndex.current) {
      prevIndex.current = i;
      setActiveIndex(i);
      onSlideChange?.(i);
    }
  });

  return { activeIndex, stepper };
}

/**
 * Progress rail — one tick per slide, `.on` at the active index. Decorative
 * (`aria-hidden`); slide state is conveyed by the slide content itself.
 */
export function ScrollyRail({
  count,
  activeIndex,
  className = "scrolly-rail",
}: {
  count: number;
  activeIndex: number;
  className?: string;
}) {
  return (
    <div className={className} aria-hidden="true">
      {Array.from({ length: count }, (_, i) => (
        <span key={i} className={`scrolly-tick${i === activeIndex ? " on" : ""}`} />
      ))}
    </div>
  );
}
