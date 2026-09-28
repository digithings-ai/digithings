"use client";

import { useEffect, useState, type CSSProperties, type RefObject } from "react";

/**
 * Block caret for the gallery-thread composer.
 *
 * `caret-shape: block` is Chromium-only, so on engines without it the native
 * caret is made transparent (see the `@supports not (caret-shape: block)`
 * rules in the reference chatbot.css) and this painted block tracks it. The
 * digichat embed likewise promotes the painted block ONLY on engines without a
 * native block caret (inside the same `@supports not (caret-shape: block)`
 * guard in product-chrome.css), so the tracking must be runtime-robust.
 *
 * Positioning is pure row/col math over the textarea value + selection offset
 * (the composer input is font-mono, so columns map to `ch` units and rows to
 * the fixed line box). Soft-wrapped visual lines are NOT unwrapped — the
 * block tracks logical lines, which is exact for the single-row embed norm.
 *
 * The textarea can mount after this overlay (the composer renders it from its
 * own lifecycle), so listeners live on the document and the textarea is
 * re-resolved per event; the initial paint retries briefly until it exists.
 */

export function caretRowCol(text: string, offset: number): { row: number; col: number } {
  const safe = Math.max(0, Math.min(Math.trunc(offset), text.length));
  const before = text.slice(0, safe);
  const row = (before.match(/\n/g) ?? []).length;
  return { row, col: safe - before.lastIndexOf("\n") - 1 };
}

const CARET_EVENTS = ["select", "input", "click", "keyup", "focusin"] as const;
const SYNC_RETRY_MS = 50;
const SYNC_RETRY_LIMIT = 40;

export function ComposerBlockCaret({
  containerRef,
}: {
  /** Ref of the wrapper holding the composer textarea. */
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  const [pos, setPos] = useState({ row: 0, col: 0 });

  useEffect(() => {
    let retries = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;

    const textarea = () => containerRef.current?.querySelector("textarea") ?? null;

    const sync = () => {
      const area = textarea();
      if (!area) return false;
      setPos(caretRowCol(area.value, area.selectionStart ?? area.value.length));
      return true;
    };

    const onEvent = (event: Event) => {
      const area = textarea();
      if (area && event.target === area) sync();
    };

    if (!sync()) {
      const retry = () => {
        if (sync() || retries >= SYNC_RETRY_LIMIT) return;
        retries += 1;
        timer = setTimeout(retry, SYNC_RETRY_MS);
      };
      timer = setTimeout(retry, SYNC_RETRY_MS);
    }

    for (const name of CARET_EVENTS) {
      document.addEventListener(name, onEvent, true);
    }

    return () => {
      if (timer) clearTimeout(timer);
      for (const name of CARET_EVENTS) {
        document.removeEventListener(name, onEvent, true);
      }
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
