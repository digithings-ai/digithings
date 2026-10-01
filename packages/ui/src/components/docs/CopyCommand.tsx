"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "../../lib/utils";
import type { CodeSample } from "./CodeTabs";

/**
 * The install command, as the primary action. OpenCode-informed: a label tab
 * strip sits on a hairline, and the command beneath it *is* the copy button —
 * no separate "copy" chrome floating beside it. A click blurs the command and
 * shows "copied" for a few seconds, then the command returns. The command is
 * split into a muted `protocol` prefix and a medium-weight ink payload; there
 * is no syntax colour. The inline form is the shared `copy-cmd` button the
 * hero clone and the module compose line both use.
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
  /**
   * Single-command form: no tab strip, no copy affordance — the whole code box
   * *is* the button ("click the box and it copies"). For a hero where the
   * command is a one-liner and the tabs would be noise. `samples[0]` is shown;
   * the rest are ignored.
   */
  inline?: boolean;
}

/** How long the command stays blurred with the copied note. */
const COPIED_MS = 2500;

async function writeClipboard(text: string): Promise<boolean> {
  const clipboard = typeof navigator === "undefined" ? undefined : navigator.clipboard;
  if (clipboard?.writeText) {
    try {
      await clipboard.writeText(text);
      return true;
    } catch {
      /* fall through */
    }
  }
  try {
    const el = document.createElement("textarea");
    el.value = text;
    el.setAttribute("readonly", "");
    el.style.position = "fixed";
    el.style.top = "-9999px";
    document.body.appendChild(el);
    el.select();
    const ok = document.execCommand("copy");
    document.body.removeChild(el);
    return ok;
  } catch {
    return false;
  }
}

function splitCommand(sample: CopyCommandSample): [string, string] {
  const { code, protocol } = sample;
  if (!protocol || !code.startsWith(protocol)) return ["", code];
  return [protocol, code.slice(protocol.length)];
}

export function CopyCommand({ samples, ariaLabel = "Install command", className, inline = false }: CopyCommandProps) {
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
    void writeClipboard(current.code).then((ok) => {
      if (!ok) return;
      setCopied(true);
      if (timer.current) clearTimeout(timer.current);
      timer.current = setTimeout(() => setCopied(false), COPIED_MS);
    });
  }

  return (
    <div className={cn(inline ? "w-fit max-w-full" : "w-full max-w-[var(--measure-prose)]", className)}>
      {inline ? null : (
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
      )}
      <button
        type="button"
        data-copied={copied ? "true" : "false"}
        onClick={copy}
        aria-label={`Copy ${inline ? "command" : `${current.label} command`}`}
        className={cn(
          "copy-cmd group relative flex cursor-pointer items-center gap-[1rem] px-[1rem] py-[0.85rem] text-left font-mono text-[0.85rem] leading-[1.5] text-ink hover:bg-surface-2",
          inline
            ? "w-auto max-w-full border border-hair bg-transparent"
            : "w-full border-x border-b border-t-0 border-hair bg-surface",
        )}
      >
        <span
          className={cn(
            "min-w-0 truncate whitespace-nowrap transition-[filter,opacity] duration-200 group-data-[copied=true]:blur-[3px] group-data-[copied=true]:opacity-40",
            inline ? "" : "flex-1",
          )}
        >
          {protocol ? <span className="text-ink-mute">{protocol}</span> : null}
          <span className="font-medium">{payload}</span>
        </span>
        <span
          aria-hidden="true"
          className="pointer-events-none absolute inset-0 hidden items-center justify-center font-medium text-ink group-data-[copied=true]:flex"
        >
          copied
        </span>
      </button>
    </div>
  );
}
