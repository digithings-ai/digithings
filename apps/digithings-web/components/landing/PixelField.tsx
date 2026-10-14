"use client";

import { useEffect, useRef } from "react";

import { mountPixelField } from "./pixel-field";

/** Canvas for the welcome field. The pointer listener hangs off the parent section. */
export function PixelField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    return mountPixelField(canvas);
  }, []);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
