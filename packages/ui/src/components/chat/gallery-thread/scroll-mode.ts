"use client";

/**
 * Whether the thread follows the answer, or leaves the scroll to the reader.
 *
 * `follow` (the default) anchors the submitted question at the top of the
 * viewport and then chases the bottom of the stream, so the answer is being
 * read as it is written. `free` never moves the viewport — not when a message
 * is sent, not while it streams — and is for readers who scroll back through
 * the transcript while a long answer arrives.
 *
 * `ThreadPrimitive.Viewport` can express both, but its defaults are the
 * half-configured state this module replaces: `autoScroll` defaults to false
 * under `turnAnchor="top"`, and while a top anchor is active during a run the
 * library deliberately stops following. So `follow` is the anchor plus our own
 * chase, and one value here fans out to the explicit prop set the viewport
 * gets.
 */

import { useEffect } from "react";

export type ScrollMode = "follow" | "free";

export const SCROLL_MODES = ["follow", "free"] as const;
export const DEFAULT_SCROLL_MODE: ScrollMode = "follow";
export const SCROLL_STORAGE_KEY = "dt-scroll";

/**
 * How close to the bottom counts as "still following". A reader who scrolls
 * up past this is reading something older, and the chase stops until they
 * come back down.
 */
const FOLLOW_BOTTOM_SLACK_PX = 24;

export function normalizeScrollMode(value: unknown): ScrollMode | undefined {
  if (value === "follow" || value === "free") return value;
  return undefined;
}

/**
 * A stored choice beats the deployment default, which beats `follow`. An
 * unknown value from either side is ignored rather than treated as a mode.
 */
export function resolveScrollMode(stored: unknown, deploy: unknown): ScrollMode {
  return (
    normalizeScrollMode(stored) ??
    normalizeScrollMode(deploy) ??
    DEFAULT_SCROLL_MODE
  );
}

export type ScrollViewportProps = {
  turnAnchor: "top" | "bottom";
  autoScroll: boolean;
  scrollToBottomOnRunStart: boolean;
  scrollToBottomOnInitialize: boolean;
  scrollToBottomOnThreadSwitch: boolean;
};

/**
 * The exact viewport prop set for a mode.
 *
 * `free` turns every trigger off explicitly. Leaving one to its default is
 * how the mode silently starts moving again — the library defaults
 * `scrollToBottomOnRunStart` and the other two to true.
 */
export function scrollModeProps(mode: ScrollMode | undefined): ScrollViewportProps {
  if (mode === "free") {
    return {
      turnAnchor: "bottom",
      autoScroll: false,
      scrollToBottomOnRunStart: false,
      scrollToBottomOnInitialize: false,
      scrollToBottomOnThreadSwitch: false,
    };
  }
  return {
    turnAnchor: "top",
    autoScroll: true,
    scrollToBottomOnRunStart: true,
    scrollToBottomOnInitialize: true,
    scrollToBottomOnThreadSwitch: true,
  };
}

export function readStoredScrollMode(
  storage?: { getItem(key: string): string | null } | null,
): ScrollMode | undefined {
  const store =
    storage === undefined
      ? typeof window === "undefined"
        ? null
        : window.localStorage
      : storage;
  if (!store) return undefined;
  try {
    return normalizeScrollMode(store.getItem(SCROLL_STORAGE_KEY));
  } catch {
    return undefined;
  }
}

export function writeStoredScrollMode(mode: ScrollMode): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(SCROLL_STORAGE_KEY, mode);
  } catch {
    /* private mode or blocked storage — the session still follows the pref */
  }
}

/**
 * Chase the bottom of the stream while the reader is at the bottom.
 *
 * The library stops following as soon as a top anchor is active and a run is
 * underway, which is why a submitted question pins and the answer then grows
 * below the fold. This reads as one rule: keep the newest line in view unless
 * the reader has taken the scroll back.
 *
 * Smoothness comes from the viewport's own `scroll-behavior: smooth`; the
 * assignments here are targets, not animations, so a stream that lands many
 * targets a second retargets the same smooth scroll instead of stacking.
 */
export function useFollowStream(
  viewport: HTMLElement | null,
  enabled: boolean,
  /**
   * Changes when a new turn starts (the message count). A send is an explicit
   * intent to read the answer, so it clears a pause the reader had taken.
   */
  resumeKey: number = 0,
): void {
  useEffect(() => {
    if (!viewport || !enabled) return;
    let paused = false;
    let lastTop = viewport.scrollTop;
    let frame = 0;

    const atBottom = () =>
      viewport.scrollHeight - viewport.scrollTop - viewport.clientHeight <=
      FOLLOW_BOTTOM_SLACK_PX;

    const chase = () => {
      frame = 0;
      if (paused) return;
      if (!atBottom()) viewport.scrollTop = viewport.scrollHeight;
    };
    const schedule = () => {
      if (frame) return;
      frame = requestAnimationFrame(chase);
    };
    const onScroll = () => {
      const top = viewport.scrollTop;
      if (atBottom()) paused = false;
      else if (top < lastTop) paused = true;
      lastTop = top;
    };

    const observer = new ResizeObserver(schedule);
    const inner = viewport.firstElementChild;
    if (inner) observer.observe(inner);
    observer.observe(viewport);
    viewport.addEventListener("scroll", onScroll, { passive: true });
    // A question sent while the reader is parked mid-transcript pins to the
    // top and then follows: sending is an explicit intent to read the answer.
    schedule();

    return () => {
      observer.disconnect();
      viewport.removeEventListener("scroll", onScroll);
      if (frame) cancelAnimationFrame(frame);
    };
  }, [viewport, enabled, resumeKey]);
}
