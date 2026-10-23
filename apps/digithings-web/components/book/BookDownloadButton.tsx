"use client";

import { useState } from "react";

import { buildBookPdf, type BuildProgress } from "@/lib/book/download-pdf";

/**
 * One-click, browser-built PDF. The artifact is generated fresh on each click:
 * a new embedding field for the cover, contents and chapter openers, in the
 * reader's current theme and palette.
 */
export default function BookDownloadButton({ className = "" }: { className?: string }) {
  const [state, setState] = useState<"idle" | "working" | "done" | "error">("idle");
  const [progress, setProgress] = useState<BuildProgress>({ done: 0, total: 0 });

  async function start() {
    if (state === "working") return;
    setState("working");
    setProgress({ done: 0, total: 0 });
    try {
      const { blob, filename } = await buildBookPdf(setProgress);
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = filename;
      link.rel = "noopener";
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000);
      setState("done");
    } catch (error) {
      console.error("book: could not build the PDF", error);
      setState("error");
    }
  }

  const working = state === "working";
  const label = working
    ? progress.total
      ? `preparing ${progress.done}/${progress.total}…`
      : "preparing the pdf…"
    : state === "error"
      ? "couldn't build the pdf — retry"
      : state === "done"
        ? "downloaded"
        : "download the pdf";

  return (
    <button
      type="button"
      onClick={start}
      disabled={working}
      aria-busy={working}
      aria-live="polite"
      className={`border-0 bg-transparent p-0 text-left disabled:opacity-60 ${className}`}
    >
      {label}
    </button>
  );
}
