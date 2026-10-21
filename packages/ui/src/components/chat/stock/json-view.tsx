"use client";

import { useState, type FC, type ReactNode } from "react";
import { formatJsonDump } from "../gallery-thread/format-json-dump";
import { cn } from "@/lib/utils";

/**
 * Tool arguments and results as full, pretty-printed JSON (DIG-4459).
 * Highlighting is a small tokenizer over the formatted text: keys, strings,
 * numbers, booleans and null get their own class, everything stays text
 * nodes (no HTML injection). Nothing is ever cut: past LONG_LINES the block
 * starts at a fixed height with its own scroll and a "Show all" toggle that
 * lifts the cap.
 */
const LONG_LINES = 18;

const TOKEN =
  /("(?:\\.|[^"\\])*")(\s*:)?|\b(true|false)\b|\b(null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

export function highlightJson(text: string): ReactNode[] {
  const out: ReactNode[] = [];
  let last = 0;
  let key = 0;
  for (const match of text.matchAll(TOKEN)) {
    const index = match.index ?? 0;
    if (index > last) out.push(text.slice(last, index));
    const [whole, str, colon, bool, nul, num] = match;
    const kind = str ? (colon ? "key" : "string") : bool ? "boolean" : nul ? "null" : num ? "number" : "";
    if (str && colon) {
      out.push(
        <span key={key++} className="aui-json-key text-sky-600 dark:text-sky-300" data-json="key">
          {str}
        </span>,
        colon,
      );
    } else {
      out.push(
        <span
          key={key++}
          data-json={kind}
          className={cn(
            kind === "string" && "aui-json-string text-emerald-700 dark:text-emerald-300",
            kind === "number" && "aui-json-number text-amber-700 dark:text-amber-300",
            (kind === "boolean" || kind === "null") &&
              "aui-json-literal text-violet-700 dark:text-violet-300",
          )}
        >
          {whole}
        </span>,
      );
    }
    last = index + whole.length;
  }
  if (last < text.length) out.push(text.slice(last));
  return out;
}

export const JsonView: FC<{
  value: unknown;
  className?: string;
  slot?: string;
}> = ({ value, className, slot = "tool-fallback-json" }) => {
  const text = formatJsonDump(value);
  const lines = text.split("\n").length;
  const long = lines > LONG_LINES;
  const [expanded, setExpanded] = useState(false);
  if (!text) return null;
  return (
    <div data-slot={`${slot}-wrap`} className="aui-json-view-wrap flex flex-col gap-1">
      <pre
        data-slot={slot}
        data-expanded={expanded ? "true" : "false"}
        data-long={long ? "true" : "false"}
        className={cn(
          "aui-json-view bg-muted/50 text-foreground/90 overflow-auto rounded-md p-2.5 font-mono text-xs whitespace-pre-wrap break-words",
          long && !expanded && "max-h-72",
          className,
        )}
      >
        {highlightJson(text)}
      </pre>
      {long ? (
        <button
          type="button"
          data-slot={`${slot}-toggle`}
          className="aui-json-view-toggle text-muted-foreground hover:text-foreground self-start text-xs underline-offset-2 hover:underline"
          onClick={() => setExpanded((open) => !open)}
        >
          {expanded ? "Collapse" : `Show all (${lines} lines)`}
        </button>
      ) : null}
    </div>
  );
};
