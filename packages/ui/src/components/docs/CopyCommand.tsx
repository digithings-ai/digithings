"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import type { CodeSample } from "./CodeTabs";

/**
 * The install command, as the primary action. OpenCode-informed: a label tab
 * strip sits on a hairline, and the command beneath it *is* the copy button —
 * no separate "copy" chrome floating beside it. The copied state rides a
 * `data-copied` attribute held for `--duration-copied` (1.5s) rather than
 * swapping label text, so the affordance is one composable hook for the
 * styling layer (D1, #4429). The command is split into a muted `protocol`
 * prefix and a medium-weight ink payload; there is no syntax colour.
 */
export interface CopyCommandSample extends CodeSample {
  /** Leading token rendered muted, e.g. `docker compose` or `git clone`. */
  protocol?: string;
}

export interface CopyCommandProps {
  samples: CopyCommandSample[];
  /** Accessible name for the tab strip. */
  ariaLabel?: string;
  className?: string;
}

/** Mirrors `--duration-copied`; a timeout needs millis, not a custom property. */
const COPIED_MS = 1500;

function splitCommand(sample: CopyCommandSample): [string, string] {
  const { code, protocol } = sample;
  if (!protocol || !code.startsWith(protocol)) return ["", code];
  return [protocol, code.slice(protocol.length)];
}

export function CopyCommand({ samples, ariaLabel = "Install command", className }: CopyCommandProps) {
  const [selected, setSelected] = useState(0);
  const [copied, setCopied] = useState(false);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const current = samples[Math.min(selected, samples.length - 1)];
  if (!current) return null;

  const [protocol, payload] = splitCommand(current);

  function copy() {
    void navigator.clipboard?.writeText(current.code).then(() => {
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), COPIED_MS);
    }).catch(() => {});
  }

  return (
    <div className={cn("w-full max-w-[var(--measure-prose)]", className)}>
      <div
        role="tablist"
        aria-label={ariaLabel}
        className="flex flex-wrap items-end gap-[1.4rem] border-b border-hair"
      >
        {samples.map((sample, index) => (
          <button
            key={sample.label}
            type="button"
            role="tab"
            aria-selected={index === selected}
            onClick={() => setSelected(index)}
            className={cn(
              "cursor-pointer border-b-2 border-transparent bg-transparent pb-[0.55rem] font-mono text-[0.8rem] tracking-[0.02em] transition-colors duration-150 ease-brand",
              index === selected ? "border-b-ink text-ink" : "text-ink-mute hover:text-ink-soft",
            )}
          >
            {sample.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        data-copied={copied ? "true" : "false"}
        onClick={copy}
        aria-label={`Copy ${current.label} command`}
        className="group flex w-full cursor-pointer items-center gap-[1rem] border-x border-b border-t-0 border-hair bg-surface px-[1rem] py-[0.85rem] text-left font-mono text-[0.85rem] leading-[1.5] transition-colors duration-150 ease-brand hover:bg-surface-2"
      >
        <span className="min-w-0 flex-1 truncate text-ink">
          {protocol ? <span className="text-ink-mute">{protocol}</span> : null}
          <span className="font-medium">{payload}</span>
        </span>
        <span className="shrink-0 text-[0.7rem] text-ink-mute">
          <span className="group-data-[copied=true]:hidden">copy</span>
          <span className="hidden text-accent group-data-[copied=true]:inline">copied</span>
        </span>
      </button>
    </div>
  );
}
