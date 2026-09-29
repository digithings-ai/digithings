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
 * Positioning is measured in pixels from the live textarea: the current
 * logical line is sliced from the value + selection offset, its width is
 * measured with a canvas 2d context using the textarea's own computed font,
 * and the block is placed at padding + measured width (minus scroll). The old
 * `col * 1ch` math drifted because the overlay's font-size (0.88rem) never
 * matched the input's (`text-sm`/`text-base`), so the error grew per
 * keystroke — behind on some skins, ahead on others. Soft-wrapped visual
 * lines are NOT unwrapped — the block tracks logical lines, which is exact
 * for the single-row embed norm.
 *
 * The textarea can mount after this overlay (the composer renders it from its
 * own lifecycle), so listeners live on the document and the textarea is
 * re-resolved per event; the initial paint retries briefly until it exists.
 * Syncs run on the next animation frame so React-controlled value /
 * selection updates have landed before we measure.
 */

export function caretRowCol(text: string, offset: number): { row: number; col: number } {
  const safe = Math.max(0, Math.min(Math.trunc(offset), text.length));
  const before = text.slice(0, safe);
  const row = (before.match(/\n/g) ?? []).length;
  return { row, col: safe - before.lastIndexOf("\n") - 1 };
}

const CARET_EVENTS = [
  "select",
  "input",
  "beforeinput",
  "click",
  "keydown",
  "keyup",
  "compositionupdate",
  "focusin",
  "scroll",
] as const;
const SYNC_RETRY_MS = 50;
const SYNC_RETRY_LIMIT = 40;

let measureCanvas: HTMLCanvasElement | null = null;

function measureTextWidth(text: string, font: string): number | null {
  if (!text) return 0;
  try {
    if (!measureCanvas && typeof document !== "undefined") {
      measureCanvas = document.createElement("canvas");
    }
    const ctx = measureCanvas?.getContext("2d");
    if (!ctx) return null;
    ctx.font = font;
    return ctx.measureText(text).width;
  } catch {
    return null;
  }
}

function px(value: string | null | undefined, fallback: number): number {
  if (!value) return fallback;
  const n = Number.parseFloat(value);
  return Number.isFinite(n) ? n : fallback;
}

/** Pixel position of the caret relative to the container. Falls back to null when unmeasurable. */
export function caretPx(
  area: HTMLTextAreaElement,
  container: HTMLElement | null,
): { left: number; top: number; height: number; width: number } | null {
  const { row, col } = caretRowCol(area.value, area.selectionStart ?? area.value.length);
  const lines = area.value.split("\n");
  const lineText = (lines[row] ?? "").slice(0, col);

  let cs: CSSStyleDeclaration | null = null;
  try {
    cs = window.getComputedStyle(area);
  } catch {
    cs = null;
  }
  const fontSize = px(cs?.fontSize, 14);
  const rawLineHeight = cs?.lineHeight ?? "";
  const lineHeight = rawLineHeight === "normal" || !rawLineHeight ? fontSize * 1.5 : px(rawLineHeight, fontSize * 1.5);
  const font =
    cs?.font && cs.font !== "" ? cs.font : `${cs?.fontWeight ?? "400"} ${fontSize}px ${cs?.fontFamily ?? "monospace"}`;

  const measured = measureTextWidth(lineText, font);
  const chWidth = measureTextWidth("0", font) ?? fontSize * 0.6;
  const textWidth = measured ?? col * chWidth;

  const paddingLeft = px(cs?.paddingLeft, 0);
  const paddingTop = px(cs?.paddingTop, 0);
  const borderLeft = px(cs?.borderLeftWidth, 0);
  const borderTop = px(cs?.borderTopWidth, 0);

  // Overlay is absolutely positioned in the relatively-positioned wrapper;
  // offsetLeft/Top pin the textarea's border box inside that wrapper.
  const baseLeft = (area.offsetLeft || 0) + borderLeft + paddingLeft;
  const baseTop = (area.offsetTop || 0) + borderTop + paddingTop;
  void container;

  return {
    left: baseLeft + textWidth - (area.scrollLeft || 0),
    top: baseTop + row * lineHeight - (area.scrollTop || 0),
    height: lineHeight,
    width: Math.max(1, chWidth),
  };
}

export function ComposerBlockCaret({
  containerRef,
}: {
  /** Ref of the wrapper holding the composer textarea. */
  containerRef: RefObject<HTMLDivElement | null>;
}) {
  const [pos, setPos] = useState({ row: 0, col: 0, left: 0, top: 0, height: 22, width: 8 });

  useEffect(() => {
    let retries = 0;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let raf = 0;
    let queued = false;

    const textarea = () => containerRef.current?.querySelector("textarea") ?? null;

    const sync = () => {
      const area = textarea();
      if (!area) return false;
      const { row, col } = caretRowCol(area.value, area.selectionStart ?? area.value.length);
      const measured = caretPx(area, containerRef.current);
      setPos(
        measured
          ? { row, col, left: measured.left, top: measured.top, height: measured.height, width: measured.width }
          : { row, col, left: col * 8, top: row * 22, height: 22, width: 8 },
      );
      return true;
    };

    const schedule = () => {
      if (queued) return;
      queued = true;
      const run = () => {
        queued = false;
        sync();
      };
      if (typeof requestAnimationFrame === "function") {
        raf = requestAnimationFrame(run);
      } else {
        run();
      }
    };

    const onEvent = (event: Event) => {
      const area = textarea();
      if (!area) return;
      if (event.target === area) {
        // Immediate sync keeps unit-test determinism (assert right after
        // dispatch); the rAF pass then re-measures after React-controlled
        // value/selection updates land, which is the live-typing fix.
        sync();
        schedule();
      } else if (event.type === "scroll") {
        schedule();
      }
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
    window.addEventListener("resize", schedule);

    return () => {
      if (timer) clearTimeout(timer);
      if (raf) cancelAnimationFrame(raf);
      queued = false;
      for (const name of CARET_EVENTS) {
        document.removeEventListener(name, onEvent, true);
      }
      window.removeEventListener("resize", schedule);
    };
  }, [containerRef]);

  return (
    <span
      aria-hidden="true"
      data-slot="aui_block-caret"
      className="aui-block-caret"
      style={
        {
          "--caret-col": pos.col,
          "--caret-row": pos.row,
          left: `${pos.left}px`,
          top: `${pos.top}px`,
          height: `${pos.height}px`,
          width: `${pos.width}px`,
        } as CSSProperties
      }
    />
  );
}
