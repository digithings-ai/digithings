"use client";

import { useLayoutEffect, useState } from "react";

/** Reset brush indices when series length changes (SIMP-028 chart drilldowns). */
export function useBrushRange(length: number) {
  const [brushStart, setBrushStart] = useState(0);
  const [brushEnd, setBrushEnd] = useState(() => Math.max(0, length - 1));

  useLayoutEffect(() => {
    if (length > 0) {
      setBrushStart(0);
      setBrushEnd(length - 1);
    }
  }, [length]);

  return { brushStart, brushEnd, setBrushStart, setBrushEnd };
}
