"use client";

import { useRef, useState, type MouseEvent, type ReactNode } from "react";
import { m, useReducedMotion } from "motion/react";
import { Button } from "@digithings/web/ui";

/**
 * Buttons & CTA states — the stock-kit button vocabulary plus a magnetic CTA
 * that eases toward the pointer and settles back on leave (disabled under
 * reduced motion). A gallery of the interactive states every surface reuses.
 *
 * Wave 1: dress is the kit Button (`@digithings/web/ui`) — primary → default,
 * ghost → ghost, quiet → outline, danger → destructive. The kit has no
 * `loading` prop, so the loading idiom is `disabled` plus an inline spinner
 * span at the call site (the states row below is the specimen).
 */
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
    <Button
      ref={ref}
      type="button"
      className="will-change-transform"
      onMouseMove={onMouseMove}
      onMouseLeave={() => setOffset({ x: 0, y: 0 })}
      render={
        <m.button
          animate={{ x: offset.x, y: offset.y }}
          transition={{ type: "spring", stiffness: 220, damping: 18, mass: 0.4 }}
        />
      }
    >
      {children}
    </Button>
  );
}

export function ButtonsCtaReference() {
  return (
    <section className="section-block buttons-cta">
      <p className="kicker">{"// buttons & ctas"}</p>
      <h2 className="title">One loud thing per viewport.</h2>
      <p className="section-copy">
        Utilitarian v0.1: the loud control is a white/ink rectangle — not an accent pill. Accent is
        reserved for focus, live state, and identity. Every sibling control recedes — a hover-only
        wash or a hairline outline. The magnetic button below is the one earned exception to the
        one-motion-moment law.
      </p>

      <div className="btn-row">
        <MagneticButton>Deploy strategy</MagneticButton>
        <Button type="button" variant="ghost">
          Read the docs
        </Button>
        <Button type="button" variant="outline">
          View source
        </Button>
      </div>

      <div className="btn-row btn-row-states">
        <Button type="button" disabled>
          Disabled
        </Button>
        <Button type="button" disabled>
          <span
            aria-hidden="true"
            className="size-[11px] shrink-0 animate-spin rounded-full border-2 border-current/30 border-t-current"
          />
          Backtesting…
        </Button>
        <Button type="button" variant="destructive">
          Kill switch
        </Button>
      </div>
    </section>
  );
}
