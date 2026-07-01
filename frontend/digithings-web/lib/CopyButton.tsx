"use client";
import { useState } from "react";

/**
 * CopyButton — a tiny "copy / copied" button shared by the chat's code blocks and
 * per-message copy affordances. Write-only clipboard access (no read), with a
 * 1.2s confirmation flip and a no-op rejection handler for blocked clipboards.
 */
export function CopyButton({
  text,
  className,
  ariaLabel,
}: {
  text: string;
  className?: string;
  ariaLabel: string;
}) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className={className}
      aria-label={ariaLabel}
      onClick={() =>
        navigator.clipboard?.writeText(text).then(
          () => {
            setCopied(true);
            setTimeout(() => setCopied(false), 1200);
          },
          () => {},
        )
      }
    >
      {copied ? "copied" : "copy"}
    </button>
  );
}
