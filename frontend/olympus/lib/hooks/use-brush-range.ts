"use client";

import { useEffect, useState } from "react";

/** Reset brush indices when series length changes (SIMP-028 chart drilldowns). */
export function useBrushRange(length: number) {
  const [brushStart, setBrushStart] = useState(0);
  const [brushEnd, setBrushEnd] = useState(0);

  useEffect(() => {
    if (length <= 0) return;
    setBrushStart(0);
    setBrushEnd(length - 1);
  }, [length]);

  return { brushStart, brushEnd, setBrushStart, setBrushEnd };
}
