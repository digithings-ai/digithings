"use client";

/**
 * 3D tilt card — mined from revolut.com's signature interactive card. The
 * surface leans in perspective toward the pointer with a specular glare that
 * tracks the cursor, then springs back flat on leave. We take the *technique*
 * (perspective transform + cursor-tracked glare), not Revolut's loud gradients:
 * a matte card on our tokens where the moving shine is the one accent read.
 * Reduced motion holds it flat and drops the glare.
 */
import { useRef } from "react";
import { Emblem } from "@digithings/web";
import { m, useMotionTemplate, useMotionValue, useReducedMotion, useSpring } from "motion/react";

const SPRING = { stiffness: 220, damping: 18, mass: 0.5 };

export function TiltCard() {
  const reduced = useReducedMotion();
  const ref = useRef<HTMLDivElement | null>(null);
  const rx = useSpring(0, SPRING);
  const ry = useSpring(0, SPRING);
  const gx = useMotionValue(50);
  const gy = useMotionValue(50);
  const glow = useSpring(0, { stiffness: 200, damping: 26 });

  const glare = useMotionTemplate`radial-gradient(circle at ${gx}% ${gy}%, color-mix(in srgb, var(--accent) 32%, transparent), transparent 58%)`;

  const onMove = (e: React.PointerEvent<HTMLDivElement>) => {
    if (reduced) return;
    const el = ref.current;
    if (!el) return;
    const r = el.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width;
    const py = (e.clientY - r.top) / r.height;
    ry.set((px - 0.5) * 26);
    rx.set(-(py - 0.5) * 20);
    gx.set(px * 100);
    gy.set(py * 100);
    glow.set(1);
  };

  const reset = () => {
    rx.set(0);
    ry.set(0);
    gx.set(50);
    gy.set(50);
    glow.set(0);
  };

  return (
    <div className="tilt-stage">
      <m.div
        ref={ref}
        className="tilt-card"
        onPointerMove={onMove}
        onPointerLeave={reset}
        style={{ rotateX: rx, rotateY: ry, transformPerspective: 900 }}
      >
        <div className="tilt-face">
          <div className="tilt-top">
            <span className="tilt-chip" aria-hidden="true" />
            <span className="tilt-brand">
              <Emblem id="digiquant" size={22} />
              digiquant
            </span>
          </div>
          <p className="tilt-number">0x00 · 4F2A · 91C3 · trend_xsec</p>
          <div className="tilt-foot">
            <span>quant · access</span>
            <span className="tilt-live">live</span>
          </div>
        </div>
        <m.span className="tilt-glare" aria-hidden="true" style={{ background: glare, opacity: glow }} />
      </m.div>
    </div>
  );
}
