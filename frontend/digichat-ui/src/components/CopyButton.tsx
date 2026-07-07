"use client";

import { useState } from "react";

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
