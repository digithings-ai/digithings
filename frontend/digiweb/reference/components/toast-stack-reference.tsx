"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { AnimatePresence, m, useReducedMotion } from "motion/react";

type ToastType = "success" | "error" | "info" | "loading";
type Toast = { id: number; type: ToastType; title: string; msg: string; ttl: number };

let counter = 0;

const ICONS: Record<ToastType, React.ReactNode> = {
  success: <path d="M5 12.5l4.5 4.5L19 7" />,
  error: <path d="M12 8v5M12 16.5v.5M12 3l9 16H3z" />,
  info: <path d="M12 11v6M12 7.5v.5" />,
  loading: <path d="M12 4a8 8 0 1 0 8 8" />,
};

/**
 * Toast stack — transient notifications that slide in at a corner, stack, and
 * retire themselves on a watchable timer, or dismiss by hand. A pending action
 * holds open with a spinner and resolves in place. Status rides the up/down
 * reads, never a livery; reduced motion drops the slide and progress bar but
 * keeps the toast. Rendered into a portal on the body.
 */
export function ToastStackReference() {
  const [toasts, setToasts] = useState<Toast[]>([]);
  const [active, setActive] = useState(false);
  const reduced = useReducedMotion();
  const timers = useRef<Map<number, number>>(new Map());

  useEffect(() => {
    const map = timers.current;
    return () => map.forEach((t) => window.clearTimeout(t));
  }, []);

  const dismiss = useCallback((id: number) => {
    setToasts((list) => list.filter((t) => t.id !== id));
    const tm = timers.current.get(id);
    if (tm) {
      window.clearTimeout(tm);
      timers.current.delete(id);
    }
  }, []);

  const arm = useCallback(
    (id: number, ttl: number) => {
      const tm = window.setTimeout(() => dismiss(id), ttl);
      timers.current.set(id, tm);
    },
    [dismiss],
  );

  const push = useCallback(
    (type: ToastType, title: string, msg: string, ttl = 4200) => {
      const id = ++counter;
      setActive(true);
      setToasts((list) => [...list.slice(-3), { id, type, title, msg, ttl }]);
      if (ttl) arm(id, ttl);
      return id;
    },
    [arm],
  );

  const deploy = useCallback(() => {
    const id = push("loading", "Deploying…", "trend_xsec → paper", 0);
    window.setTimeout(() => {
      setToasts((list) =>
        list.map((t) =>
          t.id === id
            ? { ...t, type: "success", title: "Deployed", msg: "trend_xsec is live on paper", ttl: 4200 }
            : t,
        ),
      );
      arm(id, 4200);
    }, 1700);
  }, [push, arm]);

  const stack = (
    <div className="toast-stack" role="region" aria-label="Notifications" aria-live="polite">
      <AnimatePresence initial={false}>
        {toasts.map((t) => (
          <m.div
            key={t.id}
            className={`toast toast-${t.type}`}
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
                className={t.type === "loading" ? "toast-spin" : undefined}
              >
                {ICONS[t.type]}
              </svg>
            </span>
            <div className="toast-body">
              <p className="toast-title">{t.title}</p>
              <p className="toast-msg">{t.msg}</p>
            </div>
            <button
              type="button"
              className="toast-close"
              aria-label="Dismiss"
              onClick={() => dismiss(t.id)}
            >
              <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round">
                <path d="M6 6l12 12M18 6L6 18" />
              </svg>
            </button>
            {t.ttl && !reduced ? (
              <span
                className="toast-progress"
                style={{ animationDuration: `${t.ttl}ms` }}
                aria-hidden="true"
              />
            ) : null}
          </m.div>
        ))}
      </AnimatePresence>
    </div>
  );

  return (
    <section className="section-block">
      <p className="kicker">{"// toasts"}</p>
      <h2 className="title">Transient, stacked, self-dismissing.</h2>
      <p className="section-copy">
        Notifications slide in at the corner, stack, and retire themselves on a timer you can watch
        drain — or dismiss by hand. A pending action holds open with a spinner and resolves in place.
        Status rides the up/down reads (as the terminal and order book do), never a livery. Reduced
        motion drops the slide and the progress bar but keeps the toast.
      </p>

      <div className="mt-[1.3rem] flex flex-wrap gap-[0.7rem]">
        <button type="button" className="btn-ghost" onClick={() => push("success", "Backtest complete", "PF 2.31 · saved to vault")}>
          Success
        </button>
        <button type="button" className="btn-ghost" onClick={() => push("error", "Run failed", "digikey token expired — reissue")}>
          Error
        </button>
        <button type="button" className="btn-ghost" onClick={() => push("info", "New data", "3,102 ETH-USD bars indexed")}>
          Info
        </button>
        <button type="button" className="btn-primary" onClick={deploy}>
          Deploy (loading → done)
        </button>
      </div>

      {active && typeof document !== "undefined" ? createPortal(stack, document.body) : null}
    </section>
  );
}
