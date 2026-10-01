"use client";

import { useEffect, useRef, useState } from "react";
import { useMotionSafe } from "@digithings/ui";
import { QuantWordmark } from "./QuantWordmark";

/** The closing mark above the footer, drawn at the width between the page rails (one gutter in from each) so its
 *  edges line up with the frame. It builds once, the first time it scrolls
 *  into view. Server render, no-JS and reduced motion show the finished mark. */
export function FooterWordmark() {
  const safe = useMotionSafe();
  const ref = useRef<HTMLDivElement>(null);
  const [phase, setPhase] = useState<"run" | "idle">("run");

  useEffect(() => {
    const el = ref.current;
    if (!safe || !el || typeof IntersectionObserver === "undefined") return;
    setPhase("idle");
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry?.isIntersecting) {
          io.disconnect();
          setPhase("run");
        }
      },
      { threshold: 0.35 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [safe]);

  return (
    <div className="relative z-10">
      <div
        ref={ref}
        className="mx-auto w-full max-w-[calc(var(--frame-w)+2*var(--page-pad))] overflow-x-clip px-[var(--page-pad)] pb-[clamp(1.5rem,4vw,3rem)] pt-[clamp(2.5rem,7vw,5rem)]"
      >
        <QuantWordmark phase={phase} className="block h-auto w-full fill-current text-ink" />
      </div>
    </div>
  );
}
