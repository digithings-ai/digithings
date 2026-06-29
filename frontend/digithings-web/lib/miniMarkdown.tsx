"use client";
import { Fragment, type ReactNode } from "react";
import { CopyButton } from "./CopyButton";
import { MermaidBlock } from "./MermaidBlock";

/**
 * MiniMarkdown — a deliberately minimal, XSS-safe Markdown renderer for streamed
 * model output. It builds React nodes directly and NEVER uses
 * `dangerouslySetInnerHTML`, so model text (which is attacker-influenceable via
 * prompt injection) can't inject markup — React escapes every text node. We
 * support only what a docs answer needs:
 *
 *   - fenced ```code``` blocks (with a copy button)
 *   - `inline code`
 *   - **bold**
 *   - [links](https://…) — http/https only; anything else stays literal text
 *   - line breaks
 *
 * Not full GFM (no raw HTML, images, tables) — that's the point: a tight, audited
 * surface keeps the Security gate green without a sanitizer dependency. Parsing uses
 * `String.matchAll` (no stateful `RegExp.exec` loop).
 */

// Inline spans within a single text segment. Text is auto-escaped by React.
function renderInline(text: string, keyBase: string): ReactNode[] {
  const nodes: ReactNode[] = [];
  const re = /(`[^`]+`)|(\*\*[^*]+\*\*)|(\[[^\]]+\]\(https?:\/\/[^\s)]+\))/g;
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    if (idx > last) nodes.push(<Fragment key={`${keyBase}-${k++}`}>{text.slice(last, idx)}</Fragment>);
    const tok = m[0];
    if (tok.startsWith("`")) {
      nodes.push(
        <code key={`${keyBase}-${k++}`} className="dc-code-inline">
          {tok.slice(1, -1)}
        </code>,
      );
    } else if (tok.startsWith("**")) {
      nodes.push(<strong key={`${keyBase}-${k++}`}>{tok.slice(2, -2)}</strong>);
    } else {
      const lm = tok.match(/^\[([^\]]+)\]\((https?:\/\/[^\s)]+)\)$/);
      if (lm) {
        nodes.push(
          <a key={`${keyBase}-${k++}`} href={lm[2]} target="_blank" rel="noopener noreferrer">
            {lm[1]}
          </a>,
        );
      } else {
        nodes.push(<Fragment key={`${keyBase}-${k++}`}>{tok}</Fragment>);
      }
    }
    last = idx + tok.length;
  }
  if (last < text.length) nodes.push(<Fragment key={`${keyBase}-${k++}`}>{text.slice(last)}</Fragment>);
  return nodes;
}

// A text block: paragraphs split on blank lines, single newlines become <br>.
function renderTextBlock(text: string, keyBase: string): ReactNode[] {
  return text.split(/\n{2,}/).map((para, pi) => (
    <p className="dc-md-p" key={`${keyBase}-p${pi}`}>
      {para.split("\n").map((line, li) => (
        <Fragment key={`${keyBase}-p${pi}-l${li}`}>
          {li > 0 && <br />}
          {renderInline(line, `${keyBase}-p${pi}-l${li}`)}
        </Fragment>
      ))}
    </p>
  ));
}

function CodeBlock({ code }: { code: string }) {
  return (
    <div className="dc-code-block">
      <CopyButton text={code} className="dc-code-copy" ariaLabel="Copy code" />
      <pre>
        <code>{code}</code>
      </pre>
    </div>
  );
}

export function MiniMarkdown({ text }: { text: string }) {
  const parts: ReactNode[] = [];
  // Capture the fence language so ```mermaid blocks render as diagrams.
  const re = /```([\w-]*)\n?([\s\S]*?)```/g;
  let last = 0;
  let k = 0;
  for (const m of text.matchAll(re)) {
    const idx = m.index ?? 0;
    const seg = text.slice(last, idx).trim();
    if (seg) parts.push(...renderTextBlock(seg, `seg${k++}`));
    const lang = m[1].toLowerCase();
    const body = m[2].replace(/\n$/, "");
    if (lang === "mermaid") {
      parts.push(<MermaidBlock key={`mmd${k++}`} code={body} />);
    } else {
      parts.push(<CodeBlock key={`code${k++}`} code={body} />);
    }
    last = idx + m[0].length;
  }
  const tail = text.slice(last).trim();
  if (tail) parts.push(...renderTextBlock(tail, `seg${k++}`));
  return <>{parts}</>;
}
