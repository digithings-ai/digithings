"use client";

import { useEffect, useRef, useState } from "react";
import { GROUPED_LABEL } from "./label";
import { OwnedStack, RentedStack } from "./why-stack-diagrams";
import {
  OWNED_ARC,
  OWNED_MARKS,
  OWNED_STEPS,
  RENTED_MARKS,
  RENTED_STEPS,
  allMarks,
  type WhyStep,
} from "@/lib/whyStack";

/**
 * The why-section composition (#4429 round 9), on the throwaway `/variants/why`.
 *
 * The owner's direction, after rejecting the four earlier takes: lay out the
 * rented stack, "and then you throw DigiThings [at] them and explain how it's
 * going to improve that stack."
 *
 * Round 9b (this version) follows the follow-up: "I prefer the push variant …
 * the two visuals … should be somewhat similar, just changing the components and
 * the wiring … And most importantly, the cost, everything cost, cost, cost,
 * cost, cost, and then you end up with a massive bill."
 *
 * So there is ONE stage with three layers: the rented architecture, the owned
 * architecture, and a rail that walks the steps. The push is one custom property
 * (`--why-swap`) mapping the scroll onto a lateral translate — the rented view
 * leaves to the left, the owned one arrives from the right, the rail crosses
 * between the columns. No layout flip, no reflow, nothing re-mounted.
 *
 * The swipe treatment is gone: the owner picked push, and a second treatment was
 * only ever there to be chosen between.
 *
 * Marks ACCUMULATE. The rented ledger has to visibly grow into a bill, so each
 * step lights its own boxes and keeps the previous ones lit; the owned half does
 * the same for the same reason (each step adds a slot you now run).
 *
 * Mechanics are the pattern proven three times on this page: one rAF-throttled
 * passive scroll listener writing `--why-p` and `--why-swap` straight to the DOM,
 * a pin whose track height is measured on mount and resize, and React state only
 * for the coarse step index (ten changes, not one per frame). `var(--why-p, 1)`
 * and `var(--why-swap, 1)` default to the finished state, so reduced motion and
 * no-JS get the owned half complete.
 */

const NO_MOTION = "(prefers-reduced-motion: no-preference)";

const RENTED_COUNT = RENTED_STEPS.length;
const OWNED_COUNT = OWNED_STEPS.length;
const STEPS = RENTED_COUNT + OWNED_COUNT;

/** The swap opens inside the last rented step and closes as the owned half starts. */
const SWAP_START = 0.54;
const SWAP_END = 0.62;

/** How much scroll the stage owns, in viewport heights. Ten steps, so a long one. */
const STAGE_VH = 3.6;

const clamp01 = (v: number) => Math.max(0, Math.min(1, v));

/** The union of every mark from step 0 through `index` — the accumulating set. */
function marksThrough(steps: readonly WhyStep[], index: number): string[] {
  return allMarks(...steps.slice(0, index + 1).map((step) => step.marks));
}

function usePrefersReducedMotion(): boolean {
  const [reduced, setReduced] = useState(false);
  useEffect(() => {
    if (typeof matchMedia !== "function") return;
    const mq = matchMedia("(prefers-reduced-motion: reduce)");
    const apply = () => setReduced(mq.matches);
    apply();
    mq.addEventListener("change", apply);
    return () => mq.removeEventListener("change", apply);
  }, []);
  return reduced;
}

/** One scroll listener → two custom properties + the coarse step index. */
function useStage(
  wrapRef: React.RefObject<HTMLDivElement | null>,
  pinRef: React.RefObject<HTMLDivElement | null>,
  onStep: (index: number) => void,
) {
  const stepRef = useRef(onStep);
  /* Kept in a ref so an inline callback cannot re-run the scroll effect. */
  useEffect(() => {
    stepRef.current = onStep;
  });

  useEffect(() => {
    const wrap = wrapRef.current;
    const pin = pinRef.current;
    if (!wrap || !pin) return;
    const motion = typeof matchMedia === "function" ? matchMedia(NO_MOTION) : null;

    let distance = 0;
    const measure = () => {
      distance = Math.round(window.innerHeight * STAGE_VH);
      wrap.style.height = `${pin.offsetHeight + distance}px`;
    };

    let lastStep = -1;
    const apply = (p: number) => {
      pin.style.setProperty("--why-p", p.toFixed(4));
      pin.style.setProperty(
        "--why-swap",
        clamp01((p - SWAP_START) / (SWAP_END - SWAP_START)).toFixed(4),
      );
      const index = Math.max(0, Math.min(STEPS - 1, Math.floor(p * STEPS)));
      if (index !== lastStep) {
        lastStep = index;
        stepRef.current(index);
      }
    };

    const reset = () => {
      wrap.style.height = "";
      pin.style.removeProperty("--why-p");
      pin.style.removeProperty("--why-swap");
    };

    let raf = 0;
    const onScroll = () => {
      raf = 0;
      const stickyTop = Number.parseFloat(getComputedStyle(pin).top) || 0;
      const raw = distance > 0 ? (stickyTop - wrap.getBoundingClientRect().top) / distance : 1;
      apply(clamp01(raw));
    };
    const schedule = () => {
      if (raf === 0) raf = window.requestAnimationFrame(onScroll);
    };
    const onResize = () => {
      measure();
      schedule();
    };

    const enable = () => {
      measure();
      onScroll();
      window.addEventListener("scroll", schedule, { passive: true });
      window.addEventListener("resize", onResize);
    };
    const disable = () => {
      window.removeEventListener("scroll", schedule);
      window.removeEventListener("resize", onResize);
      if (raf !== 0) window.cancelAnimationFrame(raf);
      raf = 0;
      reset();
    };

    if (!motion || motion.matches) enable();
    const onChange = () => (motion?.matches ? enable() : disable());
    motion?.addEventListener("change", onChange);
    return () => {
      motion?.removeEventListener("change", onChange);
      disable();
    };
  }, [wrapRef, pinRef]);
}

function Rail({
  steps,
  activeIndex,
  title,
  arc,
}: {
  steps: readonly WhyStep[];
  activeIndex: number;
  title: string;
  arc?: boolean;
}) {
  return (
    <div className="whyx-rail">
      {arc ? (
        <p className="whyx-arc">
          {OWNED_ARC.map((word, index) => (
            <span key={word} className="whyx-arc__item">
              {index > 0 ? <span aria-hidden="true">→</span> : null}
              {word}
            </span>
          ))}
        </p>
      ) : (
        <p className={GROUPED_LABEL}>{title}</p>
      )}
      <ol className="whyx-steps">
        {steps.map((step, index) => (
          <li
            key={step.id}
            className={`whyx-step${index === activeIndex ? " is-on" : ""}`}
            aria-current={index === activeIndex ? "true" : undefined}
          >
            <span className="whyx-step__index">{String(index + 1).padStart(2, "0")}</span>
            <span className="whyx-step__body">
              <span className="whyx-step__label">{step.label}</span>
              <span className="whyx-step__line">{step.line}</span>
            </span>
          </li>
        ))}
      </ol>
    </div>
  );
}

export function WhyStack() {
  const wrapRef = useRef<HTMLDivElement>(null);
  const pinRef = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const reduced = usePrefersReducedMotion();
  useStage(wrapRef, pinRef, setStep);

  const owned = step >= RENTED_COUNT;
  /* Marks accumulate, so the rented bill grows as the steps advance and the
     owned diagram fills rather than flashing one box at a time. Reduced motion
     is handed the finished state of both. */
  const rentedLit = reduced
    ? RENTED_MARKS
    : marksThrough(RENTED_STEPS, Math.min(step, RENTED_COUNT - 1));
  const ownedLit = reduced
    ? OWNED_MARKS
    : owned
      ? marksThrough(OWNED_STEPS, step - RENTED_COUNT)
      : [];

  return (
    <section className="whyx" data-phase={owned ? "owned" : "rented"}>
      <div ref={wrapRef} className="whyx__wrap">
        <div ref={pinRef} className="whyx__pin">
          <div className="whyx__stage">
            <div className="whyx__panel whyx__panel--rented" aria-hidden={owned}>
              <RentedStack lit={rentedLit} />
            </div>
            <div className="whyx__panel whyx__panel--owned" aria-hidden={!owned}>
              <OwnedStack lit={ownedLit} />
            </div>
            <div className="whyx__rail-slot">
              {owned ? (
                <Rail
                  steps={OWNED_STEPS}
                  activeIndex={step - RENTED_COUNT}
                  title="own the layers"
                  arc
                />
              ) : (
                <Rail steps={RENTED_STEPS} activeIndex={step} title="the stack you rent" />
              )}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export { OWNED_COUNT, RENTED_COUNT };
