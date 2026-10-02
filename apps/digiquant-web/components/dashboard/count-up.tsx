"use client";
/** Number that counts up from zero the first time it scrolls into view. The
 *  server, no-JS and reduced-motion renderings all show the final value, so the
 *  figure is never hidden or wrong; only the climb is decoration. */
import { useEffect, useRef, useState } from "react";
import { useMotionSafe } from "@digithings/ui";

const DURATION_MS = 1100;

export function CountUp({
  value,
  format,
  className,
}: {
  value: number;
  format: (n: number) => string;
  className?: string;
}) {
  const safe = useMotionSafe();
  const ref = useRef<HTMLSpanElement>(null);
  const [shown, setShown] = useState(value);

  useEffect(() => {
    const el = ref.current;
    if (!safe || !el || typeof IntersectionObserver === "undefined") {
      const id = requestAnimationFrame(() => setShown(value));
      return () => cancelAnimationFrame(id);
    }
    let raf = 0;
    const io = new IntersectionObserver(
      (entries) => {
        if (!entries.some((e) => e.isIntersecting)) return;
        io.disconnect();
        const t0 = performance.now();
        const tick = (now: number) => {
          const p = Math.min(1, (now - t0) / DURATION_MS);
          const eased = 1 - Math.pow(1 - p, 3);
          setShown(value * eased);
          if (p < 1) raf = requestAnimationFrame(tick);
        };
        raf = requestAnimationFrame(tick);
      },
      { threshold: 0.6 },
    );
    io.observe(el);
    return () => {
      io.disconnect();
      cancelAnimationFrame(raf);
    };
  }, [safe, value]);

  return (
    <span ref={ref} className={className}>
      {format(shown)}
    </span>
  );
}
