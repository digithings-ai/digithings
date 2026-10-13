"use client";

import { useEffect, useRef } from "react";

import { mountField } from "./pixel-field-core";
import { createGlassRingsSubject } from "./glass-rings-field";

/** Concept 3 canvas: nested square frames pulsing outward from center. */
export function GlassRingsField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    return mountField(canvas, createGlassRingsSubject);
  }, []);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
