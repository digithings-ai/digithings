"use client";

import { useEffect } from "react";

/**
 * Reference-counted document.body scroll lock — safe when more than one
 * overlay in the same app (a nav drawer AND a command palette, say) may
 * want the page locked at once, in any open/close order.
 *
 * A naive per-component `document.body.style.overflow = active ? "hidden"
 * : ""` effect is NOT safe here: the moment ANY ONE overlay closes, its
 * cleanup unconditionally clears the property, clobbering a second
 * overlay's lock even if that second overlay is still open — and this
 * happens regardless of which one opened first (an in-session PR review
 * on #2269 confirmed both the naive pattern's cross-overlay collision
 * itself, live-traced against NavShell's own pre-existing lock effect, and
 * that the failure survives even the "close in reverse-open order" case a
 * plain save/restore-on-mount pattern would otherwise handle).
 *
 * This instead increments/decrements a shared counter: the first `active`
 * locker captures the pre-lock value and applies "hidden"; every
 * subsequent concurrent locker is a no-op past the counter bump; only the
 * LAST one releasing restores the true original value. Correct for any
 * nesting or interleaving of open/close across every consumer.
 */
let lockCount = 0;
let previousOverflow = "";

export function useBodyScrollLock(active: boolean) {
  useEffect(() => {
    if (!active) return;
    if (lockCount === 0) {
      previousOverflow = document.body.style.overflow;
      document.body.style.overflow = "hidden";
    }
    lockCount += 1;
    return () => {
      lockCount -= 1;
      if (lockCount === 0) {
        document.body.style.overflow = previousOverflow;
      }
    };
  }, [active]);
}
