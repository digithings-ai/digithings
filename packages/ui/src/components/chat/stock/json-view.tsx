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

type JsonToken = {
  kind: "key" | "string" | "number" | "boolean" | "null";
  text: string;
  /** Text after a key: its whitespace and colon. */
  colon?: string;
};

/** Literals and numbers, tried only at the current position (sticky). */
const SCALAR = /(true|false|null)(?![\w$])|-?\d+(?:\.\d+)?(?:[eE][+-]?\d+)?/y;
const WORD_CHAR = /[\w$]/;
const SPACE = /\s/;

/**
 * One left-to-right pass over the text, no backtracking regex over strings
 * (CodeQL js/polynomial-redos): a string runs to its closing quote, or to the
 * end when it has none, so every character is read once.
 */
export function tokenizeJson(text: string): Array<string | JsonToken> {
  const out: Array<string | JsonToken> = [];
  let plain = "";
  let i = 0;
  const n = text.length;
  const flush = () => {
    if (plain) out.push(plain);
    plain = "";
  };
  while (i < n) {
    const ch = text[i];
    if (ch === '"') {
      let j = i + 1;
      while (j < n) {
        const c = text[j];
        if (c === "\\") j += 2;
        else if (c === '"') {
          j += 1;
          break;
        } else j += 1;
      }
      j = Math.min(j, n);
      const str = text.slice(i, j);
      let k = j;
      while (k < n && SPACE.test(text[k])) k += 1;
      flush();
      if (text[k] === ":") {
        out.push({ kind: "key", text: str, colon: text.slice(j, k + 1) });
        i = k + 1;
      } else {
        out.push({ kind: "string", text: str });
        i = j;
      }
      continue;
    }
    if (i === 0 || !WORD_CHAR.test(text[i - 1])) {
      SCALAR.lastIndex = i;
      const m = SCALAR.exec(text);
      if (m) {
        flush();
        const kind = m[1] === "null" ? "null" : m[1] ? "boolean" : "number";
        out.push({ kind, text: m[0] });
        i += m[0].length;
        continue;
      }
    }
    plain += ch;
    i += 1;
  }
  flush();
  return out;
}

export function highlightJson(text: string): ReactNode[] {
  let key = 0;
  const out: ReactNode[] = [];
  for (const token of tokenizeJson(text)) {
    if (typeof token === "string") {
      out.push(token);
    } else if (token.kind === "key") {
      out.push(
        <span key={key++} className="aui-json-key text-chart-1" data-json="key">
          {token.text}
        </span>,
        token.colon ?? "",
      );
    } else {
      out.push(
        <span
          key={key++}
          data-json={token.kind}
          className={cn(
            token.kind === "string" && "aui-json-string text-up",
            token.kind === "number" && "aui-json-number text-warn",
            (token.kind === "boolean" || token.kind === "null") &&
              "aui-json-literal text-chart-4",
          )}
        >
          {token.text}
        </span>,
      );
    }
  }
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
