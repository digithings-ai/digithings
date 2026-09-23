"use client";

import { useEffect, useRef, useState } from "react";
import { GROUPED_LABEL } from "./label";
import { ConventionalStack, ModularStack } from "./why-stack-diagrams";
import { OWNED_ARC, OWNED_STEPS, RENTED_STEPS, allParts, type WhyStep } from "@/lib/whyStack";

/**
 * The why-section composition (#4429 round 9), on the throwaway `/variants/why`.
 *
 * The owner's direction, after rejecting the four earlier takes:
 *
 *   "the first one should be like the conventional stack or the off-the-shelf
 *    stack. And we show what it would look like and how much it would cost for
 *    each component … And then DigiThings is suggesting a different approach,
 *    one that's well-informed, modular, scalable, affordable, and customized …
 *    for the conventional stack, we have this menu on the right side, the visual
 *    on the left side, and you go through each step of what it is. And then we
 *    kind of create a visual where we swipe that around and the text moves to the
 *    left side, and that's where you show DigiThings. And a new visual appears on
 *    the right, so it just gets swiped out of the way, and then DigiThings comes
 *    in. … That's basically laying out the trap, and then you throw DigiThings
 *    out [at] them and explain how it's going to improve that stack."
 *
 * So there is ONE stage with three layers: the rented diagram on the left, the
 * owned diagram on the right, and a single ten-step rail that begins on the
 * right and ends on the left. The swap is one custom property (`--why-swap`)
 * mapping the scroll onto a lateral translate, so the rail crosses the stage
 * while the rented visual leaves and the owned one arrives — no layout flip, no
 * reflow, nothing re-mounted.
 *
 * `variant` is the only difference between the two treatments on the page:
 * `swipe` slides the rail across and cross-fades the visuals in place; `push`
 * sends the rented visual off the left edge while the owned one pushes in from
 * the right. Same DOM, same copy, different motion.
 *
 * Mechanics are the pattern proven three times on this page: one rAF-throttled
 * passive scroll listener writing `--why-p` and `--why-swap` straight to the DOM,
 * a pin whose track height is measured on mount and resize, and React state only
 * for the coarse step index (ten changes, not one per frame). `var(--why-p, 1)`
 * and `var(--why-swap, 1)` default to the finished state, so reduced motion and
 * no-JS get the owned half complete and stacked.
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
      pin.style.setProperty("--why-swap", clamp01((p - SWAP_START) / (SWAP_END - SWAP_START)).toFixed(4));
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

export function WhyStack({ variant = "swipe" }: { variant?: "swipe" | "push" }) {
  const wrapRef = useRef<HTMLDivElement>(null);
  const pinRef = useRef<HTMLDivElement>(null);
  const [step, setStep] = useState(0);
  const reduced = usePrefersReducedMotion();
  useStage(wrapRef, pinRef, setStep);

  const owned = step >= RENTED_COUNT;
  const marks = reduced
    ? allParts([...RENTED_STEPS, ...OWNED_STEPS])
    : owned
      ? OWNED_STEPS[step - RENTED_COUNT].parts
      : RENTED_STEPS[step].parts;
  const progress = STEPS > 1 ? step / (STEPS - 1) : 1;

  return (
    <section className="whyx" data-variant={variant} data-phase={owned ? "owned" : "rented"}>
      <div ref={wrapRef} className="whyx__wrap">
        <div ref={pinRef} className="whyx__pin">
          <div className="whyx__stage">
            <div className="whyx__panel whyx__panel--rented" aria-hidden={owned}>
              <ConventionalStack marks={marks} progress={progress} />
            </div>
            <div className="whyx__panel whyx__panel--owned" aria-hidden={!owned}>
              <ModularStack marks={marks} progress={progress} />
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
