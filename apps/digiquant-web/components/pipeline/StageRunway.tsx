"use client";

import { useEffect, useRef, type ReactNode } from "react";
import { runwayProgress } from "@/lib/scroll-stack";
import { DECK_GAP, DECK_MOTION_QUERY, deckPose, deckVisibleCount } from "./deck-motion";

const LEAD_VIEWPORTS = 0.4;

/** The pipeline deck. Static layout is one card on a phone, two from 1024px, three from
 *  1440px — every card stays in the document, with its copy intact. When motion is allowed
 *  on a desktop width, scroll plays the deck: the visible cards stack, slide into their
 *  slots, and each next card stacks onto the right before the row slides on. Reduced
 *  motion leaves the grid alone. */
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
    const mq = window.matchMedia(DECK_MOTION_QUERY);
    let raf = 0;

    const cards = () => Array.from(list.current?.children ?? []) as HTMLElement[];
    const settle = () => {
      const ol = list.current;
      if (ol) {
        ol.style.position = "";
        ol.style.height = "";
      }
      for (const el of cards()) {
        el.style.position = "";
        el.style.width = "";
        el.style.top = "";
        el.style.left = "";
        el.style.opacity = "";
        el.style.transform = "";
        el.style.zIndex = "";
        el.style.pointerEvents = "";
        el.removeAttribute("aria-hidden");
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
      const items = cards();
      if (items.length === 0) return;
      const visible = deckVisibleCount(window.innerWidth);
      const cardW = (ol.clientWidth - DECK_GAP * (visible - 1)) / visible;
      if (!(cardW > 0)) return;
      ol.style.position = "relative";
      for (const el of items) {
        el.style.position = "absolute";
        el.style.top = "0";
        el.style.left = "0";
        el.style.width = `${cardW}px`;
      }
      const deckH = Math.max(...items.map((el) => el.offsetHeight));
      if (ol.style.height !== `${deckH}px`) ol.style.height = `${deckH}px`;

      const pinTop = parseFloat(getComputedStyle(pane).top) || 0;
      const top = run.getBoundingClientRect().top - pinTop;
      const progress = runwayProgress(top, run.offsetHeight, pane.offsetHeight, window.innerHeight * LEAD_VIEWPORTS);
      const deckWidth = visible * cardW + DECK_GAP * (visible - 1);
      items.forEach((el, i) => {
        const pose = deckPose(i, items.length, visible, progress, cardW, DECK_GAP);
        const hidden = pose.opacity <= 0.02 || pose.x >= deckWidth - 8 || pose.x <= -24;
        el.style.opacity = String(pose.opacity);
        el.style.transform = `translate3d(${pose.x}px, ${pose.y}px, 0)`;
        el.style.zIndex = String(pose.z);
        el.style.pointerEvents = hidden ? "none" : "";
        if (hidden) el.setAttribute("aria-hidden", "true");
        else el.removeAttribute("aria-hidden");
      });
    };

    const schedule = () => {
      if (!raf) raf = requestAnimationFrame(apply);
    };
    schedule();
    const observed = cards();
    const ro = new ResizeObserver(schedule);
    for (const el of observed) ro.observe(el);
    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule);
    mq.addEventListener("change", schedule);
    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", schedule);
      mq.removeEventListener("change", schedule);
      settle();
    };
  }, []);

  return (
    <div ref={runway} className="min-w-0 lg:motion-safe:h-[calc(100svh+220svh)] lg:motion-safe:overflow-x-clip">
      <div
        ref={stage}
        className="flex min-w-0 flex-col gap-4 lg:motion-safe:sticky lg:motion-safe:top-[var(--nav-shell-h,62px)] lg:motion-safe:min-h-[calc(100svh-var(--nav-shell-h,62px))] lg:motion-safe:justify-center"
      >
        {intro}
        <ol
          ref={list}
          aria-label={label}
          className="m-0 grid min-w-0 list-none grid-cols-1 gap-4 p-0 lg:grid-cols-2 min-[1440px]:grid-cols-3"
        >
          {children}
        </ol>
        {outro}
      </div>
    </div>
  );
}
