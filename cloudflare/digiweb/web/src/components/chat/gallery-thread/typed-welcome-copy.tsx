"use client";

import { useEffect, useLayoutEffect, useState } from "react";

import { DIGI_CHAT_READY_EVENT, hasDigichatReady } from "../boot-signal";

/** ms per character for the welcome body typewriter. */
const TYPE_MS = 18;
/** Beat between body lines once a line finishes typing. */
const LINE_PAUSE_MS = 260;
/** Fallback when no boot loader ever signals (surfaces without a boot). */
const READY_FALLBACK_MS = 3000;

type Reveal = { line: number; chars: number } | null;

/** Layout effect on the client so the static copy never flashes before the
 *  typewriter takes over; passive effect during SSR to stay warning-free. */
const useIsoLayoutEffect =
  typeof window === "undefined" ? useEffect : useLayoutEffect;

function prefersReducedMotion(): boolean {
  return (
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * The welcomeBody lines under the headline. Every line keeps its full copy
 * in the DOM from the first frame (SSR, no-JS, screen readers, tests); on
 * the client a typewriter reveals the copy in place — the untyped remainder
 * holds its space invisibly, so nothing reflows while it types. When the app
 * mounts its boot animation (which types the same copy), the hero stays
 * static; otherwise the typewriter waits for the boot's painted signal so
 * the type is not spent behind an overlay.
 */
export function TypedWelcomeCopy({ lines }: { lines: readonly string[] }) {
  const content = lines.join("\n");
  const [reveal, setReveal] = useState<Reveal>(null);

  useIsoLayoutEffect(() => {
    const copy = content.length === 0 ? [] : content.split("\n");
    if (copy.length === 0 || prefersReducedMotion()) {
      setReveal(null);
      return;
    }

    // Lab switch: `?hero=instant` reveals the hero in one shot (paired with
    // the boot-lab alternates; the classic boot keeps typing the copy itself).
    if (new URLSearchParams(window.location.search).get("hero") === "instant") {
      setReveal(null);
      return;
    }

    // The universal boot animation types this copy itself; the hero renders
    // settled under it. Heroes mounted later (new chat) type as usual. Skip
    // markers parked inside hidden containers (Next.js streams a hidden
    // staging duplicate of the shell that keeps the marker forever).
    const bootVisible = [
      ...document.querySelectorAll("[data-digichat-boot]"),
    ].some((element) => element.closest("[hidden]") === null);
    if (bootVisible) {
      setReveal(null);
      return;
    }

    let line = 0;
    let chars = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    let started = false;

    const schedule = (ms: number) => {
      timer = setTimeout(tick, ms);
    };

    function tick() {
      if (cancelled) return;
      if (chars >= copy[line].length) {
        if (line + 1 >= copy.length) {
          setReveal(null);
          return;
        }
        line += 1;
        chars = 0;
        setReveal({ line, chars });
        schedule(LINE_PAUSE_MS);
        return;
      }
      chars += 1;
      setReveal({ line, chars });
      schedule(TYPE_MS);
    }

    const start = () => {
      if (started) return;
      started = true;
      setReveal({ line: 0, chars: 0 });
      schedule(TYPE_MS);
    };

    // The typewriter waits for the boot's painted signal so the type is not
    // spent behind a host overlay; standalone surfaces (and older builds)
    // start now, or after the fallback when no signal ever arrives.
    let onReady: (() => void) | undefined;
    let fallback: ReturnType<typeof setTimeout> | undefined;
    if (window.parent === window || hasDigichatReady()) {
      start();
    } else {
      onReady = () => start();
      window.addEventListener(DIGI_CHAT_READY_EVENT, onReady, { once: true });
      fallback = setTimeout(start, READY_FALLBACK_MS);
    }

    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
      if (onReady) window.removeEventListener(DIGI_CHAT_READY_EVENT, onReady);
      if (fallback !== undefined) clearTimeout(fallback);
    };
  }, [content]);

  return (
    <>
      {lines.map((line, index) => {
        const settled = reveal === null || index < reveal.line;
        const typing = reveal !== null && index === reveal.line;
        return (
          <p
            key={`${index}:${line}`}
            className="aui-thread-welcome-copy"
            aria-label={settled ? undefined : line}
          >
            {settled ? (
              line
            ) : typing ? (
              <>
                {line.slice(0, reveal.chars)}
                <span className="aui-thread-welcome-caret" aria-hidden="true" />
                <span className="aui-thread-welcome-ghost" aria-hidden="true">
                  {line.slice(reveal.chars)}
                </span>
              </>
            ) : (
              <span className="aui-thread-welcome-ghost" aria-hidden="true">
                {line}
              </span>
            )}
          </p>
        );
      })}
    </>
  );
}
