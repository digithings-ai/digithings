"use client";

import { useEffect, useLayoutEffect, useState } from "react";

/** ms per character for the welcome body typewriter. */
const TYPE_MS = 18;
/** Beat between body lines once a line finishes typing. */
const LINE_PAUSE_MS = 260;

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
 * holds its space invisibly, so nothing reflows while it types.
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

    let line = 0;
    let chars = 0;
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;

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

    setReveal({ line: 0, chars: 0 });
    schedule(TYPE_MS);

    return () => {
      cancelled = true;
      if (timer !== undefined) clearTimeout(timer);
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
