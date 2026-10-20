"use client";

/**
 * Square overlay scrollbar for scroll containers whose native bar is hidden.
 *
 * Safari draws its overlay scrollbar as an OS capsule and ignores
 * `::-webkit-scrollbar` shape rules, so the native bar is hidden and this
 * square track/thumb is painted instead. It follows scroll position, keyboard
 * scrolling and size changes, and can be dragged. `width` sets the depth tier:
 * the thread viewport is widest, menus next, tool-call dumps narrowest.
 */

import { useEffect, useState, type PointerEvent as ReactPointerEvent, type RefObject } from "react";

import { cn } from "../../lib/utils";

export function OverlayScrollbar({
  targetRef,
  width = 6,
  className,
}: {
  targetRef: RefObject<HTMLElement | null>;
  width?: number;
  className?: string;
}) {
  const [thumb, setThumb] = useState<{ top: number; height: number } | null>(null);

  useEffect(() => {
    const el = targetRef.current;
    if (!el) return;
    const update = () => {
      const { scrollTop, scrollHeight, clientHeight } = el;
      if (scrollHeight <= clientHeight + 1) {
        setThumb(null);
        return;
      }
      const height = Math.max(12, Math.round((clientHeight / scrollHeight) * clientHeight));
      const maxTop = clientHeight - height;
      const maxScroll = scrollHeight - clientHeight;
      setThumb({
        top: maxScroll > 0 ? Math.round((scrollTop / maxScroll) * maxTop) : 0,
        height,
      });
    };
    update();
    el.addEventListener("scroll", update, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [targetRef]);

  if (!thumb) return null;

  const startDrag = (event: ReactPointerEvent<HTMLDivElement>) => {
    const el = targetRef.current;
    if (!el) return;
    event.preventDefault();
    const startY = event.clientY;
    const startScroll = el.scrollTop;
    const maxScroll = el.scrollHeight - el.clientHeight;
    const track = el.clientHeight - thumb.height;
    const move = (e: PointerEvent) => {
      if (track <= 0) return;
      el.scrollTop = startScroll + ((e.clientY - startY) / track) * maxScroll;
    };
    const end = () => {
      window.removeEventListener("pointermove", move);
      window.removeEventListener("pointerup", end);
    };
    window.addEventListener("pointermove", move);
    window.addEventListener("pointerup", end, { once: true });
  };

  return (
    <div className={cn("aui-overlay-scroll", className)} style={{ width }} aria-hidden>
      <div
        className="aui-overlay-thumb"
        style={{ top: thumb.top, height: thumb.height }}
        onPointerDown={startDrag}
      />
    </div>
  );
}
