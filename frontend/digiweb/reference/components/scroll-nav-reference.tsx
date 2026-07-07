"use client";

import { useRef, useState } from "react";
import { m, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";

const LINKS = ["Product", "Pricing", "Docs", "Changelog"];

/**
 * Scroll-aware nav — a sticky bar that gains a hairline and blurred backdrop
 * only after the hero clears, and yields to reading direction: it hides on
 * scroll-down and returns on scroll-up. State is driven from a contained demo
 * frame's own scroll so the bar pins inside it; reduced motion drops the
 * slide transition.
 */
export function ScrollNavReference() {
  const stageRef = useRef<HTMLDivElement | null>(null);
  const [solid, setSolid] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [lastY, setLastY] = useState(0);
  const reduce = useReducedMotion();

  // Drive the scroll-aware state from the demo frame's own scroll, not the
  // page — so the sticky nav pins inside the frame and can never float up
  // over the section copy above it.
  const { scrollY } = useScroll({ container: stageRef });

  useMotionValueEvent(scrollY, "change", (y) => {
    setSolid(y > 24);
    setHidden(y > lastY + 4 && y > 120);
    setLastY(y);
  });

  return (
    <section className="section-block relative">
      <p className="kicker">{"// nav"}</p>
      <h2 className="title">Quiet, literal, scroll-aware.</h2>
      <p className="section-copy">
        Nav gains a hairline + backdrop only after the hero clears, and yields to reading
        direction — hides on scroll-down, returns on scroll-up. No logo animation, no shadow
        drama. Scroll inside the frame below to see it react.
      </p>

      <div
        className="relative mt-[1.2rem] h-[22rem] overflow-y-auto rounded-[12px] border border-hair bg-surface scroll-pt-0"
        ref={stageRef}
      >
        <m.div
          className={`scroll-nav${solid ? " solid" : ""}`}
          animate={{ y: hidden ? -72 : 0 }}
          transition={reduce ? { duration: 0 } : { duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="font-mono text-[0.78rem] text-ink">digithings</span>
          <ul className="m-0 flex list-none gap-[1.1rem] p-0 font-mono text-[0.72rem] text-ink-soft max-[900px]:hidden">
            {LINKS.map((link) => (
              <li key={link}>{link}</li>
            ))}
          </ul>
          <button type="button" className="btn-quiet ml-auto">
            Sign in
          </button>
        </m.div>

        <div
          className="flex max-w-[46ch] flex-col gap-[1.6rem] px-[1.4rem] pb-[1.4rem] text-ink-soft"
          aria-hidden="true"
        >
          <p className="mt-[0.6rem] font-display text-[2rem] text-ink">Scroll ↓</p>
          <p>Past the hero, the bar takes on a hairline and a blurred backdrop.</p>
          <p>Keep scrolling down and it retreats out of the way.</p>
          <p>Scroll back up and it returns — reading direction wins.</p>
          <p>The mark never animates; the surface just settles.</p>
          <p>No shadow drama, no shrink-on-scroll, no logo reveal.</p>
          <p>Chrome should be legible and then get out of the way.</p>
          <p>One quiet element, doing exactly what the scroll implies.</p>
        </div>
      </div>
    </section>
  );
}
