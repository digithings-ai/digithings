"use client";

/**
 * Horizontal row for example questions. Its scrollbar is thin and stays
 * hidden until the row is hovered, focused or scrolled (styles in
 * chat-aui.css, `.aui-suggestion-scroll`). Chrome does not repaint a
 * `::-webkit-scrollbar-thumb` when only `:hover` changes, so the row sets
 * `data-hover` / `data-focus` itself, and `data-scrolling` for a moment after
 * each scroll so touch and trackpad users see where they are.
 */

import {
  forwardRef,
  useCallback,
  useEffect,
  useRef,
  type FocusEvent,
  type HTMLAttributes,
  type PointerEvent,
  type UIEvent,
} from "react";

import { cn } from "../../lib/utils";

const REVEAL_MS = 900;

export const SuggestionScrollRow = forwardRef<HTMLDivElement, HTMLAttributes<HTMLDivElement>>(
  function SuggestionScrollRow(
    { className, onScroll, onPointerEnter, onPointerLeave, onFocus, onBlur, ...props },
    ref,
  ) {
    const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

    useEffect(
      () => () => {
        if (timer.current) clearTimeout(timer.current);
      },
      [],
    );

    const handleScroll = useCallback(
      (event: UIEvent<HTMLDivElement>) => {
        const el = event.currentTarget;
        el.dataset.scrolling = "true";
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
          delete el.dataset.scrolling;
        }, REVEAL_MS);
        onScroll?.(event);
      },
      [onScroll],
    );

    return (
      <div
        ref={ref}
        className={cn("aui-suggestion-scroll overflow-x-auto", className)}
        onScroll={handleScroll}
        onPointerEnter={(event: PointerEvent<HTMLDivElement>) => {
          if (event.pointerType === "mouse") event.currentTarget.dataset.hover = "true";
          onPointerEnter?.(event);
        }}
        onPointerLeave={(event: PointerEvent<HTMLDivElement>) => {
          delete event.currentTarget.dataset.hover;
          onPointerLeave?.(event);
        }}
        onFocus={(event: FocusEvent<HTMLDivElement>) => {
          event.currentTarget.dataset.focus = "true";
          onFocus?.(event);
        }}
        onBlur={(event: FocusEvent<HTMLDivElement>) => {
          if (!event.currentTarget.contains(event.relatedTarget as Node | null)) {
            delete event.currentTarget.dataset.focus;
          }
          onBlur?.(event);
        }}
        {...props}
      />
    );
  },
);
