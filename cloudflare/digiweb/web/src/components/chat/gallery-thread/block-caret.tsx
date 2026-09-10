"use client";

import { useEffect, useState, type CSSProperties, type RefObject } from "react";

/**
 * Safari-compatible block caret for the gallery-thread composer.
 *
 * `caret-shape: block` is Chromium-only, so on other engines the native caret
 * is made transparent (see the `@supports not (caret-shape: block)` rules in
 * the reference chatbot.css) and this painted block tracks it instead.
 * Chromium keeps the native block caret and the overlay stays hidden.
 *
 * Positioning is pure row/col math over the textarea value + selection offset
 * (the composer input is font-mono, so columns map to `ch` units and rows to
 * the fixed line box). Soft-wrapped visual lines are NOT unwrapped — the
 * block tracks logical lines, which is exact for the single-row embed norm.
 */

export function caretRowCol(text: string, offset: number): { row: number; col: number } {
  const safe = Math.max(0, Math.min(Math.trunc(offset), text.length));
  const before = text.slice(0, safe);
  const row = (before.match(/\n/g) ?? []).length;
  return { row, col: safe - before.lastIndexOf("\n") - 1 };
}

export function ComposerBlockCaret({
  containerRef,
}: {
  /** Ref of the wrapper holding the composer textarea. */
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  const [pos, setPos] = useState({ row: 0, col: 0 });

  useEffect(() => {
    const area = containerRef.current?.querySelector("textarea");
    if (!area) return;
    const sync = () =>
      setPos(caretRowCol(area.value, area.selectionStart ?? area.value.length));
    sync();
    const events = ["select", "input", "click", "keyup"] as const;
    for (const name of events) area.addEventListener(name, sync);
    return () => {
      for (const name of events) area.removeEventListener(name, sync);
    };
  }, [containerRef]);

  return (
    <span
      aria-hidden="true"
      data-slot="aui_block-caret"
      className="aui-block-caret"
      style={{ "--caret-col": pos.col, "--caret-row": pos.row } as CSSProperties}
    />
  );
}
