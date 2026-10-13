"use client";

import { useEffect, useRef } from "react";

import { mountField } from "./pixel-field-core";
import { createModuleGraphSubject } from "./module-graph-field";

/** Concept 1 canvas: module graph with fixed nodes and flow pulses. */
export function ModuleGraphField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    return mountField(canvas, createModuleGraphSubject);
  }, []);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
