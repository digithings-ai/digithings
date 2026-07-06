"use client";

import { useState } from "react";
import { m, useMotionValueEvent, useScroll } from "motion/react";

const LINKS = ["Product", "Pricing", "Docs", "Changelog"];

export function ScrollNavReference() {
  const { scrollYProgress } = useScroll();
  const [solid, setSolid] = useState(false);
  const [hidden, setHidden] = useState(false);
  const [lastY, setLastY] = useState(0);

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    const y = progress * document.documentElement.scrollHeight;
    setSolid(y > 40);
    setHidden(y > lastY + 4 && y > 200);
    setLastY(y);
  });

  return (
    <section className="section-block scroll-nav-demo">
      <p className="kicker">{"// nav"}</p>
      <h2 className="title">Quiet, literal, scroll-aware.</h2>
      <p className="section-copy">
        Nav gains a hairline + backdrop only after the hero clears, and yields to reading
        direction — hides on scroll-down, returns on scroll-up. No logo animation, no shadow
        drama. Scroll this app to see it react.
      </p>

      <m.div
        className={`scroll-nav${solid ? " solid" : ""}`}
        animate={{ y: hidden ? -64 : 0 }}
        transition={{ duration: 0.24, ease: [0.22, 1, 0.36, 1] }}
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
    </section>
  );
}
