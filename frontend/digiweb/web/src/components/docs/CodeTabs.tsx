"use client";
import { useState } from "react";

/**
 * Docs code affordances: a hover-revealed copy button, a bare copyable code
 * block, and a label-tabbed code switcher. Presentation-generic — samples
 * arrive as `{ label, code }`, so language naming ("curl" vs "bash") is the
 * caller's business. Token-backed utilities carry the look; the hover-reveal
 * combinator for the copy button lives in styles/docs.css.
 */

export interface CodeSample {
  /** Tab label, e.g. "curl", "Python", "TypeScript". */
  label: string;
  code: string;
}

/** Tiny write-only "copy / copied" clipboard button (1.2s confirmation flip). */
function DocsCopyButton({ text, ariaLabel }: { text: string; ariaLabel: string }) {
  const [copied, setCopied] = useState(false);
  return (
    <button
      type="button"
      className="docs-code-copy cursor-pointer rounded-[6px] border border-hair bg-surface/80 px-[0.4rem] py-[0.12rem] font-mono text-[0.7rem] text-ink-mute hover:text-ink"
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

/** Pre-formatted code block with the hover-revealed copy affordance. */
export function DocsCodeBlock({
  code,
  copyLabel = "Copy code",
}: {
  code: string;
  copyLabel?: string;
}) {
  return (
    <div className="doc-code relative mt-[0.5rem]">
      <DocsCopyButton text={code} ariaLabel={copyLabel} />
      <pre className="m-0 overflow-x-auto rounded-[9px] border border-hair bg-ink/6 px-[0.8rem] py-[0.7rem]">
        <code className="whitespace-pre font-mono text-[0.8rem] text-ink">{code}</code>
      </pre>
    </div>
  );
}

/** Label-tabbed code block — one sample visible at a time, copyable. */
export function CodeTabs({ samples }: { samples: CodeSample[] }) {
  const [sel, setSel] = useState(0);
  if (!samples.length) return null;
  const cur = samples[Math.min(sel, samples.length - 1)];
  return (
    <div className="mt-[0.3rem] flex flex-col gap-[0.3rem]">
      {samples.length > 1 && (
        <div className="flex gap-[0.2rem]" role="tablist">
          {samples.map((s, i) => (
            <button
              key={s.label}
              type="button"
              role="tab"
              aria-selected={i === sel}
              className={`cursor-pointer rounded-t-[7px] border border-transparent px-[0.6rem] py-[0.2rem] font-mono text-[0.72rem] transition-colors duration-150 ease-brand ${
                i === sel ? "bg-accent-weak text-ink" : "text-ink-mute hover:text-ink-soft"
              }`}
              onClick={() => setSel(i)}
            >
              {s.label}
            </button>
          ))}
        </div>
      )}
      <DocsCodeBlock code={cur.code} copyLabel={`Copy ${cur.label} example`} />
    </div>
  );
}
