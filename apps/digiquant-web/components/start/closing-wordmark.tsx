"use client";

import { useEffect, useState } from "react";
import { QuantWordmark } from "../../app/_chrome/QuantWordmark";

/** Closing wordmark: the hero's bar-built lockup, replayed when it scrolls into
 *  view (the build animation is CSS on mount, so it would otherwise finish
 *  unseen at page load). Server render, no-JS and reduced motion all show the
 *  finished wordmark; only an armed, off-screen wordmark is withheld. */
type Phase = "shown" | "armed" | "play";

export function ClosingWordmark({ className }: { className?: string }) {
  const [phase, setPhase] = useState<Phase>("shown");

  useEffect(() => {
    if (typeof IntersectionObserver === "undefined") return;
    if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    const host = document.getElementById("start-wordmark");
    if (!host) return;
    const io = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setPhase("play");
          io.disconnect();
        } else {
          setPhase("armed");
        }
      },
      { threshold: 0.4 },
    );
    io.observe(host);
    return () => io.disconnect();
  }, []);

  return (
    <div id="start-wordmark" className="aspect-[79/10] w-full">
      {phase === "armed" ? null : <QuantWordmark className={className} />}
    </div>
  );
}
