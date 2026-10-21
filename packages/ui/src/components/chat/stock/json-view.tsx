"use client";

import type { FC, ReactNode } from "react";
import { formatJsonDump } from "../gallery-thread/format-json-dump";
import { cn } from "@/lib/utils";

/**
 * Tool arguments and results as full, pretty-printed JSON (DIG-4459).
 * Highlighting is a small tokenizer over the formatted text: keys, strings,
 * numbers, booleans and null get their own class, everything stays text
 * nodes (no HTML injection). Nothing is ever cut: the block sits in a
 * max-height scroll area (18rem), no expand button (Chris, 21 Oct).
 */

// The closing quote is optional so an unterminated string still matches to
// the end in one pass instead of rescanning from every later quote (CodeQL
// js/polynomial-redos). formatJsonDump output is always well formed anyway.
const TOKEN =
  /("(?:\\.|[^"\\])*"?)(\s*:)?|\b(true|false)\b|\b(null)\b|(-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?)/g;

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
        <span key={key++} className="aui-json-key text-chart-1" data-json="key">
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
            kind === "string" && "aui-json-string text-up",
            kind === "number" && "aui-json-number text-warn",
            (kind === "boolean" || kind === "null") &&
              "aui-json-literal text-chart-4",
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
  if (!text) return null;
  return (
    <pre
      data-slot={slot}
      className={cn(
        "aui-json-view bg-muted/50 text-foreground/90 max-h-72 overflow-auto overscroll-contain rounded-md p-2.5 font-mono text-xs whitespace-pre-wrap break-words",
        className,
      )}
    >
      {highlightJson(text)}
    </pre>
  );
};
