"use client";

import { useCallback, useState } from "react";
import { ToastStack, type ToastItem, type ToastTone } from "@digithings/web";

/**
 * Toast stack — transient notifications that slide in at a corner, stack, and
 * retire themselves on a watchable timer, or dismiss by hand. A pending action
 * holds open with a spinner and resolves in place. Status rides the up/down
 * reads, never a livery; reduced motion drops the slide and progress bar but
 * keeps the toast. Rendered into a portal on the body.
 * Consumes the shared <ToastStack/> primitive from @digithings/web — the
 * toast LIST stays app-owned (this demo's push/deploy state), the primitive
 * only renders it and fires onDismiss.
 */
let counter = 0;

export function ToastStackReference() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  const dismiss = useCallback((id: ToastItem["id"]) => {
    setToasts((list) => list.filter((t) => t.id !== id));
  }, []);

  const push = useCallback((tone: ToastTone, title: string, message: string, ttlMs = 4200) => {
    const id = ++counter;
    setToasts((list) => [...list.slice(-3), { id, tone, title, message, ttlMs }]);
    return id;
  }, []);

  const deploy = useCallback(() => {
    const id = push("loading", "Deploying…", "trend_xsec → paper", 0);
    window.setTimeout(() => {
      setToasts((list) =>
        list.map((t) =>
          t.id === id
            ? { ...t, tone: "success", title: "Deployed", message: "trend_xsec is live on paper", ttlMs: 4200 }
            : t,
        ),
      );
    }, 1700);
  }, [push]);

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

      <ToastStack toasts={toasts} onDismiss={dismiss} />
    </section>
  );
}
