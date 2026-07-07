"use client";

import { useRef, useState, type MouseEvent, type ReactNode } from "react";
import { m, useReducedMotion } from "motion/react";

type MagneticButtonProps = { children: ReactNode };

function MagneticButton({ children }: MagneticButtonProps) {
  const ref = useRef<HTMLButtonElement>(null);
  const [offset, setOffset] = useState({ x: 0, y: 0 });
  const reduceMotion = useReducedMotion();

  function onMouseMove(event: MouseEvent<HTMLButtonElement>) {
    if (reduceMotion || !ref.current) return;
    const rect = ref.current.getBoundingClientRect();
    const x = (event.clientX - rect.left - rect.width / 2) * 0.28;
    const y = (event.clientY - rect.top - rect.height / 2) * 0.32;
    setOffset({ x, y });
  }

  return (
    <m.button
      ref={ref}
      type="button"
      className="btn-primary btn-magnetic"
      onMouseMove={onMouseMove}
      onMouseLeave={() => setOffset({ x: 0, y: 0 })}
      animate={{ x: offset.x, y: offset.y }}
      transition={{ type: "spring", stiffness: 220, damping: 18, mass: 0.4 }}
    >
      {children}
    </m.button>
  );
}

export function ButtonsCtaReference() {
  return (
    <section className="section-block buttons-cta">
      <p className="kicker">{"// buttons & ctas"}</p>
      <h2 className="title">One loud thing per viewport.</h2>
      <p className="section-copy">
        Graphite and x.ai both run a single saturated CTA against an otherwise flat surface —
        every other control recedes to hairline outlines. The magnetic button below is the one
        earned exception to law 05 (one motion moment): a CTA may track the cursor because it is
        the single decision on the page.
      </p>

      <div className="btn-row">
        <MagneticButton>Deploy strategy</MagneticButton>
        <button type="button" className="btn-ghost">
          Read the docs
        </button>
        <button type="button" className="btn-quiet">
          View source
        </button>
      </div>

      <div className="btn-row btn-row-states">
        <button type="button" className="btn-primary" disabled>
          Disabled
        </button>
        <button type="button" className="btn-primary btn-loading" disabled>
          <span className="btn-spinner" aria-hidden="true" />
          Backtesting…
        </button>
        <button type="button" className="btn-danger">
          Kill switch
        </button>
      </div>
    </section>
  );
}
