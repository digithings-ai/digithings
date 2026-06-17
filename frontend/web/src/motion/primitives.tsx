"use client";
/**
 * Shared Framer Motion vocabulary. All transitions use the brand easing.
 * Everything degrades under prefers-reduced-motion via useMotionSafe().
 * Animate transform / opacity / pathLength only.
 */
import {
  LazyMotion,
  domAnimation,
  m,
  useReducedMotion,
  type Variants,
  type Transition,
} from "framer-motion";
import { type ReactNode } from "react";

export const EASE: [number, number, number, number] = [0.22, 1, 0.36, 1];
export const baseTransition: Transition = { duration: 0.6, ease: EASE };

/** True when motion is allowed (not reduced). */
export function useMotionSafe(): boolean {
  return !useReducedMotion();
}

/** Wrap an app/tree once so `m.*` components have animation features (small bundle). */
export function MotionProvider({ children }: { children: ReactNode }) {
  return <LazyMotion features={domAnimation} strict>{children}</LazyMotion>;
}

export const revealVariants: Variants = {
  hidden: { opacity: 0, y: 16 },
  show: { opacity: 1, y: 0, transition: baseTransition },
};

export const staggerParent: Variants = {
  hidden: {},
  show: { transition: { staggerChildren: 0.06, delayChildren: 0.04 } },
};

/** Fade + rise when scrolled into view (once). Falls back to static if reduced. */
export function Reveal({
  children,
  className,
  as = "div",
  delay = 0,
}: {
  children: ReactNode;
  className?: string;
  as?: keyof typeof m;
  delay?: number;
}) {
  const safe = useMotionSafe();
  const Comp = m[as] as typeof m.div;
  if (!safe) return <Comp className={className}>{children}</Comp>;
  return (
    <Comp
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      variants={{ hidden: { opacity: 0, y: 16 }, show: { opacity: 1, y: 0, transition: { ...baseTransition, delay } } }}
    >
      {children}
    </Comp>
  );
}

/** Stagger container; children should use <Reveal> or variants={revealVariants}. */
export function Stagger({ children, className }: { children: ReactNode; className?: string }) {
  const safe = useMotionSafe();
  if (!safe) return <div className={className}>{children}</div>;
  return (
    <m.div
      className={className}
      initial="hidden"
      whileInView="show"
      viewport={{ once: true, margin: "0px 0px -10% 0px" }}
      variants={staggerParent}
    >
      {children}
    </m.div>
  );
}

/** One-shot hero entrance on mount (no scroll). */
export function HeroEntrance({ children, className }: { children: ReactNode; className?: string }) {
  const safe = useMotionSafe();
  if (!safe) return <div className={className}>{children}</div>;
  return (
    <m.div className={className} initial="hidden" animate="show" variants={staggerParent}>
      {children}
    </m.div>
  );
}

export { m };
