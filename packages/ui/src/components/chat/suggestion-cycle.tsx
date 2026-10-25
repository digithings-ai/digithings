"use client";

/**
 * The empty-state starter chips, capped and cycled.
 *
 * A tenant defines its own starter list (the house tenant 8, OCC 8, DataTap 5)
 * and the welcome used to print all of them, which turned the empty state into
 * a wall of prompts. Four is what fits on one line of reading; the rest are
 * reached by cycling, so every defined starter is still seen.
 *
 * The cycle is deliberately polite:
 * - it pauses while the pointer is over the chips or focus is inside them,
 *   because a list that changes under the cursor is a list you cannot click;
 * - it stops for good once the conversation has started or the composer holds
 *   text, so the prompts never move under someone who is reading them while
 *   composing;
 * - it never starts under `prefers-reduced-motion: reduce`, which pins the
 *   first group;
 * - the timer is cleared on unmount and whenever those conditions stop it, so
 *   nothing ticks in the background.
 *
 * The group size is constant, so a swap never reflows the row: the wrapper is
 * keyed by the group offset and the chips re-run their existing entrance fade
 * (house duration tokens) instead of the row growing or shrinking.
 */

import {
  createContext,
  useContext,
  useEffect,
  useMemo,
  useState,
  type FocusEventHandler,
  type PointerEventHandler,
  type ReactNode,
} from "react";

/** How many starter chips are on screen at once. */
export const VISIBLE_SUGGESTIONS = 4;

/** How long a group stays before the next one fades in. */
export const SUGGESTION_CYCLE_MS = 8_000;

/**
 * The window of `all` starting at `offset`, wrapping. Returns the whole list
 * when it already fits, so a tenant with 3 starters is never padded.
 */
export function suggestionWindow(
  all: readonly string[],
  offset: number,
): readonly string[] {
  if (all.length <= VISIBLE_SUGGESTIONS) return all;
  const start = ((offset % all.length) + all.length) % all.length;
  return Array.from(
    { length: VISIBLE_SUGGESTIONS },
    (_, index) => all[(start + index) % all.length]!,
  );
}

/** Reduced-motion, read directly: the cycle is a JS timer, so CSS cannot stop it. */
function usePrefersReducedMotion(): boolean {
  // Lazy read: the group on screen is the same either way (offset 0), so the
  // client's real preference cannot desync the server markup.
  const [reduced, setReduced] = useState(
    () =>
      typeof window !== "undefined" &&
      Boolean(window.matchMedia?.("(prefers-reduced-motion: reduce)").matches),
  );
  useEffect(() => {
    if (typeof window === "undefined" || !window.matchMedia) return;
    const query = window.matchMedia("(prefers-reduced-motion: reduce)");
    const onChange = (event: MediaQueryListEvent) => setReduced(event.matches);
    query.addEventListener?.("change", onChange);
    return () => query.removeEventListener?.("change", onChange);
  }, []);
  return reduced;
}

/** Handlers a chip row spreads so the cycle pauses while it is being read. */
export type SuggestionCycleHandlers = {
  onPointerEnter: PointerEventHandler;
  onPointerLeave: PointerEventHandler;
  onFocus: FocusEventHandler;
  onBlur: FocusEventHandler;
};

export type SuggestionCycle = {
  /** The group currently on screen. */
  visible: readonly string[];
  /** Index of the group's first chip — also the row's remount key. */
  offset: number;
  /** True while hovered or focused: the cycle is held, not stopped. */
  paused: boolean;
  handlers: SuggestionCycleHandlers;
};

/**
 * Cap `all` to {@link VISIBLE_SUGGESTIONS} and advance through it every
 * {@link SUGGESTION_CYCLE_MS}.
 *
 * `stopped` is the caller's "the user is no longer looking at a fresh empty
 * state" signal (thread has messages, composer has text).
 */
export function useSuggestionCycle(
  all: readonly string[],
  { stopped = false }: { stopped?: boolean } = {},
): SuggestionCycle {
  const [offset, setOffset] = useState(0);
  const [hovered, setHovered] = useState(false);
  const [focused, setFocused] = useState(false);
  const reduced = usePrefersReducedMotion();

  const paused = hovered || focused;
  const cycles = all.length > VISIBLE_SUGGESTIONS;
  const active = cycles && !stopped && !paused && !reduced;

  useEffect(() => {
    if (!active) return;
    const timer = setInterval(
      () => setOffset((current) => current + VISIBLE_SUGGESTIONS),
      SUGGESTION_CYCLE_MS,
    );
    return () => clearInterval(timer);
  }, [active]);

  const handlers = useMemo<SuggestionCycleHandlers>(
    () => ({
      onPointerEnter: () => setHovered(true),
      onPointerLeave: () => setHovered(false),
      onFocus: () => setFocused(true),
      onBlur: () => setFocused(false),
    }),
    [],
  );

  const visible = useMemo(
    () => suggestionWindow(all, offset),
    [all, offset],
  );

  return { visible, offset, paused, handlers };
}

const SuggestionCycleContext = createContext<SuggestionCycle | null>(null);

/** Mounts the cycle above the skins so every renderer shares one timer. */
export function SuggestionCycleProvider({
  value,
  children,
}: {
  value: SuggestionCycle;
  children: ReactNode;
}) {
  return (
    <SuggestionCycleContext.Provider value={value}>
      {children}
    </SuggestionCycleContext.Provider>
  );
}

/**
 * What a skin's chip row needs: the remount key (so the group fades in) and
 * the pause handlers. Surfaces mounted without the provider still render —
 * they simply never cycle.
 */
export function useSuggestionGroup(): {
  groupKey: number;
  handlers: SuggestionCycleHandlers;
} {
  const cycle = useContext(SuggestionCycleContext);
  return useMemo(
    () => ({
      groupKey: cycle?.offset ?? 0,
      handlers: cycle?.handlers ?? NO_HANDLERS,
    }),
    [cycle],
  );
}

const NO_HANDLERS: SuggestionCycleHandlers = {
  onPointerEnter: () => {},
  onPointerLeave: () => {},
  onFocus: () => {},
  onBlur: () => {},
};

/**
 * Has the visitor left the fresh empty state? Reads the assistant-ui runtime
 * directly so the shell that owns the starter list can stop the cycle without
 * sitting inside the runtime provider. Defensive on purpose: a runtime double
 * or an SSR pass without a live thread simply reports "not started".
 */
export function useThreadActivity(
  runtime: { thread?: unknown } | null | undefined,
): { started: boolean; typed: boolean } {
  const thread = runtime?.thread as
    | {
        getState?: () => { messages?: readonly unknown[] } | undefined;
        subscribe?: (callback: () => void) => (() => void) | void;
        composer?: { getState?: () => { text?: string } | undefined };
      }
    | undefined;
  const [started, setStarted] = useState(false);
  const [typed, setTyped] = useState(false);

  useEffect(() => {
    if (typeof thread?.getState !== "function") return;
    const read = () => {
      let messages: readonly unknown[] | undefined;
      let text: string | undefined;
      try {
        messages = thread.getState?.()?.messages;
        text = thread.composer?.getState?.()?.text;
      } catch {
        return;
      }
      setStarted((messages?.length ?? 0) > 0);
      setTyped((text?.trim().length ?? 0) > 0);
    };
    // Deferred out of the synchronous effect body —
    // react-hooks/set-state-in-effect.
    queueMicrotask(read);
    const unsubscribe = thread.subscribe?.(read);
    return () => {
      if (typeof unsubscribe === "function") unsubscribe();
    };
  }, [thread]);

  return useMemo(() => ({ started, typed }), [started, typed]);
}
