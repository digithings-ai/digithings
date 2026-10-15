"use client";

import { useEffect, useRef } from "react";

import { createEmbeddingSubject, parseSeed, randomSeed } from "./embedding-map";
import { mountField } from "./pixel-field-core";

/**
 * Canvas for the welcome field: a new embedding-space map on every load.
 * `?seed=` reproduces one; the seed in use is on the canvas as `data-seed`.
 * The pointer listener hangs off the parent section.
 */
export function PixelField() {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    const seed = parseSeed(new URLSearchParams(window.location.search).get("seed")) ?? randomSeed();
    canvas.dataset.seed = String(seed);
    return mountField(canvas, createEmbeddingSubject(seed));
  }, []);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
