"use client";

import { useRef, useState } from "react";
import { m, useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";

const LINKS = ["Product", "Pricing", "Docs", "Changelog"];

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
    <section className="section-block scroll-nav-demo">
      <p className="kicker">{"// nav"}</p>
      <h2 className="title">Quiet, literal, scroll-aware.</h2>
      <p className="section-copy">
        Nav gains a hairline + backdrop only after the hero clears, and yields to reading
        direction — hides on scroll-down, returns on scroll-up. No logo animation, no shadow
        drama. Scroll inside the frame below to see it react.
      </p>

      <div className="scroll-nav-stage" ref={stageRef}>
        <m.div
          className={`scroll-nav${solid ? " solid" : ""}`}
          animate={{ y: hidden ? -72 : 0 }}
          transition={reduce ? { duration: 0 } : { duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
        >
          <span className="scroll-nav-mark">digithings</span>
          <ul>
            {LINKS.map((link) => (
              <li key={link}>{link}</li>
            ))}
          </ul>
          <button type="button" className="btn-quiet scroll-nav-cta">
            Sign in
          </button>
        </m.div>

        <div className="scroll-nav-page" aria-hidden="true">
          <p className="scroll-nav-hero">Scroll ↓</p>
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
