"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { runwayProgress, stageProgress } from "@/lib/scroll-stack";

const LEAD_VIEWPORTS = 0.4;
const DESKTOP_MOTION = "(min-width: 1024px) and (prefers-reduced-motion: no-preference)";

/** The pipeline's stage cards, driven by scroll. On desktop the stage pins under the nav and
 *  scrolling through the runway slides each card in from the right, one after another, until
 *  all of them are settled in their slots. Narrow screens, reduced motion and no-JS get the
 *  settled layout: nothing is hidden until this effect runs. Cards are moved with inline
 *  transform and opacity, written straight to the elements from the scroll handler. */
export function StageRunway({
  intro,
  outro,
  label,
  children,
}: {
  intro: ReactNode;
  outro: ReactNode;
  label: string;
  children: ReactNode;
}) {
  const runway = useRef<HTMLDivElement>(null);
  const stage = useRef<HTMLDivElement>(null);
  const list = useRef<HTMLOListElement>(null);

  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_MOTION);
    let raf = 0;

    const cards = () => Array.from(list.current?.children ?? []) as HTMLElement[];
    const settle = () => {
      for (const el of cards()) {
        el.style.opacity = "";
        el.style.transform = "";
      }
    };

    const apply = () => {
      raf = 0;
      const run = runway.current;
      const pane = stage.current;
      const ol = list.current;
      if (!run || !pane || !ol) return;
      if (!mq.matches) {
        settle();
        return;
      }
      const pinTop = parseFloat(getComputedStyle(pane).top) || 0;
      const top = run.getBoundingClientRect().top - pinTop;
      const progress = runwayProgress(top, run.offsetHeight, pane.offsetHeight, window.innerHeight * LEAD_VIEWPORTS);
      const items = cards();
      const trackRight = ol.offsetLeft + ol.offsetWidth;
      items.forEach((el, i) => {
        const q = stageProgress(progress, i, items.length);
        const travel = (trackRight - el.offsetLeft + 24) * (1 - q);
        el.style.opacity = String(q);
        el.style.transform = `translate3d(${travel}px, 0, 0)`;
      });
    };

    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(apply);
    };
    schedule();
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    mq.addEventListener("change", schedule);
    return () => {
      cancelAnimationFrame(raf);
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      mq.removeEventListener("change", schedule);
      settle();
    };
  }, []);

  return (
    <div ref={runway} className="lg:h-[calc(100svh+130svh)] lg:overflow-x-clip">
      <div
        ref={stage}
        className="flex flex-col gap-3 lg:sticky lg:top-[var(--nav-shell-h,62px)] lg:min-h-[calc(100svh-var(--nav-shell-h,62px))] lg:justify-center"
      >
        {intro}
        <ol
          ref={list}
          aria-label={label}
          className="m-0 grid list-none auto-cols-[min(70vw,15rem)] grid-flow-col gap-2 overflow-x-auto p-0 snap-x lg:auto-cols-auto lg:grid-flow-row lg:grid-cols-7 lg:overflow-visible"
        >
          {children}
        </ol>
        {outro}
      </div>
    </div>
  );
}
