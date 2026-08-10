"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, m, useReducedMotion } from "motion/react";

/**
 * ToastStack — the corner notification stack promoted from the design
 * reference (chrome/toasts), as an imperative-free, props-driven primitive:
 * the APP owns the toast list (push/update/remove in its own state — there is
 * no global toast() singleton here) and passes `toasts` + `onDismiss`. The
 * stack renders them sliding in at the corner; a toast with `ttlMs` retires
 * itself on a watchable drain timer (the component fires `onDismiss(id)` at
 * expiry — remove it from state there), one without holds open (the pending /
 * spinner case) and resolves in place when the app swaps its tone and ttl.
 *
 * Status rides the up/down reads (success/error), never a livery. Reduced
 * motion drops the slide and the progress bar but keeps the toast (ttl
 * dismissal still runs). Renders into a document.body portal by default
 * (mount-gated, so SSR/hydration are safe); `portal={false}` renders in
 * place for contained demos.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/effects-chrome.css";
 *                 @source "<path-to>/digiweb/web/src/components/effects-chrome";
 */
export type ToastTone = "success" | "error" | "info" | "loading";

export type ToastItem = {
  id: string | number;
  tone: ToastTone;
  /** Mono headline — "Backtest complete". */
  title: string;
  /** Optional detail line — "PF 2.31 · saved to vault". */
  message?: string;
  /** Auto-dismiss after this many ms; omit or 0 to hold open. */
  ttlMs?: number;
};

export type ToastStackProps = {
  toasts: ToastItem[];
  /** Remove the toast from app state — fired by the ✕ and by ttl expiry. */
  onDismiss: (id: ToastItem["id"]) => void;
  /** Render into a document.body portal (default) or in place. */
  portal?: boolean;
  ariaLabel?: string;
  className?: string;
};

const ICONS: Record<ToastTone, ReactNode> = {
  success: <path d="M5 12.5l4.5 4.5L19 7" />,
  error: <path d="M12 8v5M12 16.5v.5M12 3l9 16H3z" />,
  info: <path d="M12 11v6M12 7.5v.5" />,
  loading: <path d="M12 4a8 8 0 1 0 8 8" />,
};

export function ToastStack({
  toasts,
  onDismiss,
  portal = true,
  ariaLabel = "Notifications",
  className,
}: ToastStackProps) {
  const reduced = useReducedMotion();
  const [mounted, setMounted] = useState(false);
  const timers = useRef<Map<ToastItem["id"], { ttl: number; timer: number }>>(new Map());
  const onDismissRef = useRef(onDismiss);

  useEffect(() => {
    onDismissRef.current = onDismiss;
  }, [onDismiss]);

  useEffect(() => setMounted(true), []);

  // Arm/re-arm ttl timers declaratively: a toast whose ttl changed (the
  // loading → success resolve-in-place move) gets a fresh timer; departed
  // toasts get theirs cleared.
  useEffect(() => {
    const map = timers.current;
    const live = new Set(toasts.map((t) => t.id));
    for (const [id, entry] of map) {
      if (!live.has(id)) {
        window.clearTimeout(entry.timer);
        map.delete(id);
      }
    }
    for (const t of toasts) {
      const ttl = t.ttlMs ?? 0;
      const entry = map.get(t.id);
      if (entry && entry.ttl === ttl) continue;
      if (entry) window.clearTimeout(entry.timer);
      if (ttl > 0) {
        map.set(t.id, {
          ttl,
          timer: window.setTimeout(() => {
            map.delete(t.id);
            onDismissRef.current(t.id);
          }, ttl),
        });
      } else {
        map.delete(t.id);
      }
    }
  }, [toasts]);

  useEffect(() => {
    const map = timers.current;
    return () => {
      map.forEach((entry) => window.clearTimeout(entry.timer));
      map.clear();
    };
  }, []);

  const stack = (
    <div
      className={`toast-stack${className ? ` ${className}` : ""}`}
      role="region"
      aria-label={ariaLabel}
      aria-live="polite"
    >
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <m.div
            key={t.id}
            className={`toast toast-${t.tone}`}
            initial={reduced ? { opacity: 0 } : { opacity: 0, x: 40, scale: 0.96 }}
            animate={reduced ? { opacity: 1 } : { opacity: 1, x: 0, scale: 1 }}
            exit={reduced ? { opacity: 0 } : { opacity: 0, x: 40, scale: 0.96 }}
            transition={{ duration: 0.26 }}
          >
            <span className="toast-icon" aria-hidden="true">
              <svg
                viewBox="0 0 24 24"
                width="16"
                height="16"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
                strokeLinejoin="round"
                className={t.tone === "loading" ? "toast-spin" : undefined}
              >
                {ICONS[t.tone]}
              </svg>
            </span>
            <div className="toast-body">
              <p className="toast-title">{t.title}</p>
              {t.message ? <p className="toast-msg">{t.message}</p> : null}
            </div>
            <button
              type="button"
              className="toast-close"
              aria-label="Dismiss"
              onClick={() => onDismiss(t.id)}
            >
              <svg
                viewBox="0 0 24 24"
                width="13"
                height="13"
                fill="none"
                stroke="currentColor"
                strokeWidth="1.8"
                strokeLinecap="round"
              >
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            {t.ttlMs && !reduced ? (
              <span
                className="toast-progress"
                style={{ animationDuration: `${t.ttlMs}ms` }}
                aria-hidden="true"
              />
            ) : null}
          </m.div>
        ))}
      </AnimatePresence>
    </div>
  );

  if (!portal) return stack;
  if (!mounted) return null;
  return createPortal(stack, document.body);
}
