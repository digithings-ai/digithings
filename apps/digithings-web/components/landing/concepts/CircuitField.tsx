"use client";

import { useEffect, useRef } from "react";

import { mountField } from "./pixel-field-core";
import { createCircuitSubject } from "./circuit-field";

/** Concept 2 canvas: PCB-style traces with traveling signal pulses. */
export function CircuitField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    return mountField(canvas, createCircuitSubject);
  }, []);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
