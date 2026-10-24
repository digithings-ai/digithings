"use client";

/**
 * A code block inside a chapter (U17).
 *
 * The MDX `pre` mapping is the only place a chapter assembles a code block, so
 * the affordances live here instead of being repeated in every chapter:
 *
 *  - the `<pre>` is a keyboard-reachable scroll container. A block can be wider
 *    than the reading column, and a reader who has no trackpad still has to be
 *    able to reach the end of the line (WCAG 2.1.1).
 *  - a bar above the block says "scroll" only while the block actually
 *    overflows, so the hint is true on a phone and absent on a wide screen.
 *  - "copy" writes the block's text to the clipboard and reports the result in
 *    a live region rather than only changing the button's label.
 */

import { useCallback, useEffect, useRef, useState } from "react";

type Status = "idle" | "copied" | "failed";

export default function BookCode({ children, className, ...rest }: React.HTMLAttributes<HTMLPreElement>) {
  const preRef = useRef<HTMLPreElement>(null);
  const [overflowing, setOverflowing] = useState(false);
  const [status, setStatus] = useState<Status>("idle");
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const measure = useCallback(() => {
    const pre = preRef.current;
    if (pre) setOverflowing(pre.scrollWidth > pre.clientWidth + 1);
  }, []);

  useEffect(() => {
    measure();
    const pre = preRef.current;
    if (!pre || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(pre);
    return () => observer.disconnect();
  }, [measure]);

  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);

  const copy = async () => {
    const text = preRef.current?.innerText ?? "";
    try {
      await navigator.clipboard.writeText(text);
      setStatus("copied");
    } catch {
      setStatus("failed");
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setStatus("idle"), 2000);
  };

  return (
    <div className="book-code mb-6 border-hair border" data-overflow={overflowing ? "x" : undefined}>
      <div className="book-code__bar flex items-center justify-between gap-3 border-hair border-b px-3 py-1">
        <span className="book-code__hint font-mono text-[0.7rem] text-ink-soft">scroll</span>
        <button type="button" onClick={copy} className="book-code__copy font-mono text-[0.7rem] text-ink-soft hover:text-ink focus-visible:outline focus-visible:outline-1 focus-visible:outline-offset-2 focus-visible:outline-ink">
          {status === "copied" ? "copied" : "copy"}
        </button>
      </div>
      <pre
        ref={preRef}
        tabIndex={0}
        aria-label="code block"
        className={`m-0 overflow-x-auto p-4 font-mono text-[0.85rem] leading-[1.45] text-ink ${className ?? ""}`}
        {...rest}
      >
        {children}
      </pre>
      <span aria-live="polite" className="sr-only">
        {status === "copied" ? "code copied" : status === "failed" ? "copy failed, select the text instead" : ""}
      </span>
    </div>
  );
}
