"use client";

import { useEffect, useRef } from "react";

import { mountField } from "./pixel-field-core";
import { createEmbeddingSubject, type EmbeddingLayout } from "./embedding-field";

/** DIG-3319 round 2 canvas: the embedding-space map in one of three compositions. */
export function EmbeddingField({ layout }: { layout: EmbeddingLayout }) {
  const ref = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const canvas = ref.current;
    if (!canvas) return;
    return mountField(canvas, createEmbeddingSubject(layout));
  }, [layout]);

  return <canvas ref={ref} className="pixel-field" aria-hidden="true" />;
}
