"use client";

import { useState } from "react";

import { copyMarkdownWithFallback } from "../transcript-markdown";

/**
 * CopyButton — a tiny "copy / copied" button shared by the chat's code blocks and
 * per-message copy affordances. Write-only clipboard access first; on embed/
 * blocked clipboards falls back to `.md` download → parent `digichat:copy`
 * postMessage → selectable textarea (#3465). Never a silent no-op.
 */
export function CopyButton({
  text,
  className,
  ariaLabel,
  filename,
}: {
  text: string;
  className?: string;
  ariaLabel: string;
  /** Filename used when the embed fallback downloads `.md`. */
  filename?: string;
}) {
  const [label, setLabel] = useState<"copy" | "copied" | "saved">("copy");
  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      onClick={() => {
        void copyMarkdownWithFallback(text, { filename: filename ?? "digichat-answer.md" }).then(
          (result) => {
            setLabel(result === "download" ? "saved" : "copied");
            setTimeout(() => setLabel("copy"), 1200);
          },
        );
      }}
    >
      {label}
    </button>
  );
}
