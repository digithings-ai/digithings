"use client";

import { useState } from "react";

/** Brush indices for Recharts mini-map (SIMP-028). Remount the consumer with `key={length}` when series size changes. */
export function useBrushRange(length: number) {
  const [brushStart, setBrushStart] = useState(0);
  const [brushEnd, setBrushEnd] = useState(() => Math.max(0, length - 1));

  return { brushStart, brushEnd, setBrushStart, setBrushEnd };
}
