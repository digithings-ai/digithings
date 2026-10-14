"use client";

import { useEffect, useState } from "react";
import { LANDING_SECTIONS } from "./sections";

/**
 * The landing page's wayfinding (Refs #4429): a terminal path set vertically
 * in the left gutter, outside the page rails, with one tick per band. The
 * path names the band under the middle of the viewport, and each tick jumps
 * to its band. It only renders where the gutter is wide enough to hold it.
 */

const SECTIONS = LANDING_SECTIONS;

export function SectionRail() {
  const [active, setActive] = useState(-1);

  useEffect(() => {
    let frame = 0;
    const read = () => {
      const mid = window.innerHeight / 2;
      let next = -1;
      SECTIONS.forEach((section, index) => {
        const el = document.getElementById(section.id);
        if (el && el.getBoundingClientRect().top <= mid) next = index;
      });
      setActive(next);
    };
    const onScroll = () => {
      cancelAnimationFrame(frame);
      frame = requestAnimationFrame(read);
    };
    read();
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    return () => {
      cancelAnimationFrame(frame);
      window.removeEventListener("scroll", onScroll);
      window.removeEventListener("resize", onScroll);
    };
  }, []);

  const current = active >= 0 ? SECTIONS[active] : null;

  return (
    <nav
      aria-label="Page sections"
      className="fixed top-1/2 z-30 hidden -translate-x-1/2 -translate-y-1/2 flex-col items-center gap-[1.1rem] font-mono text-[0.68rem] text-ink-mute min-[1400px]:flex"
      style={{ left: "calc((100vw - var(--frame-w) - 2 * var(--page-pad)) / 4)" }}
    >
      <ol className="m-0 flex list-none flex-col items-center p-0">
        {SECTIONS.map((section, index) => (
          <li key={section.id}>
            <a
              href={`#${section.id}`}
              aria-label={section.label}
              aria-current={index === active ? "location" : undefined}
              className="group flex h-[0.8rem] w-[1.4rem] items-center justify-center"
            >
              <span
                className={`block h-px transition-[width,background-color] duration-300 ${
                  index === active
                    ? "w-[1.1rem] bg-ink"
                    : "w-[0.5rem] bg-ink-mute group-hover:w-[0.8rem] group-hover:bg-ink-soft"
                }`}
              />
            </a>
          </li>
        ))}
      </ol>
      <span
        aria-hidden="true"
        className="rotate-180 whitespace-nowrap tracking-[0.04em] [writing-mode:vertical-rl]"
      >
        ~/digithings
        {current ? <span className="text-ink">/{current.label}</span> : null}
      </span>
    </nav>
  );
}
