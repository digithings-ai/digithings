"use client";

import { useEffect, useState } from "react";
import { getWarmupPhase, subscribeWarmup, warmupStatusText, type WarmupPhase } from "@/lib/warmup-gate";

/** Small boot status line shown while sleeping chat services wake up. */
export function WarmupStatus() {
  const [ph, setPh] = useState<WarmupPhase>(getWarmupPhase());
  useEffect(() => subscribeWarmup(setPh), []);
  const text = warmupStatusText(ph);
  if (!text) return null;
  return (
    <div
      role="status"
      aria-live="polite"
      data-slot="digichat-warmup-status"
      className="text-muted-foreground pointer-events-none absolute inset-x-0 top-2 z-30 flex items-center justify-center gap-2 text-xs"
    >
      <span className="bg-current inline-block size-1.5 animate-pulse rounded-full" aria-hidden />
      {text}
    </div>
  );
}
