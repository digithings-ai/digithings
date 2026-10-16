"use client";
/**
 * Mermaid diagram block for <ChatMarkdown> — a ```mermaid fence in streamed
 * model output, drawn as an SVG in the token palette. Promoted up from
 * digichat-ui's MermaidBlock so both chat surfaces draw the same diagram;
 * this is the canon copy.
 *
 * Four things it owes the canon:
 *
 *  1. TOKENS, NEVER MERMAID'S PALETTE. Every built-in mermaid theme hard-codes
 *     its own hues, so we run `theme: "base"` — the one palette that lets every
 *     themeVariable through — and fill it from the *computed* value of
 *     --ink / --surface / --hair / --accent read off this figure. Reading off
 *     the figure rather than :root means a livery scope (`.accent-digichat`)
 *     or a nested [data-theme] resolves exactly the colours the surrounding
 *     turn resolves.
 *  2. BOTH THEMES, LIVE. A MutationObserver on <html data-theme> re-reads the
 *     tokens and re-renders, so flipping the theme toggle repaints the diagram
 *     instead of leaving a dark graph on a paper surface.
 *  3. NO JS, NO PROBLEM. The source ships inside a <pre> in the server markup
 *     and is only replaced once mermaid has actually drawn something. A reader
 *     without JS (or before hydration) sees the diagram source, never an empty
 *     box; a parse failure keeps that same <pre> and never throws into the
 *     transcript.
 *  4. LAZY. mermaid is ~2.9 MB raw (parser + d3 + dagre + cytoscape), so it is
 *     imported *inside* the effect — `await import("mermaid")` — and lands in
 *     its own async chunk that no page pays for until a diagram appears.
 *
 * Safety: the source is attacker-influenceable model text, so it runs under
 * `securityLevel: "strict"` — mermaid disables HTML labels, drops click
 * handlers/`script` directives, and passes its own output through the DOMPurify
 * copy it bundles before returning it. `suppressErrorRendering` additionally
 * stops a malformed graph injecting mermaid's error-bomb SVG into the
 * transcript. `mermaid.render()` therefore hands back an already-sanitized SVG
 * *string*, which is why this is the one justified innerHTML on the chat
 * surfaces (`htmlLabels: false` is set again below so a config merge cannot
 * quietly re-enable raw label HTML). Motion lives in styles/chat-core.css
 * behind a prefers-reduced-motion guard.
 */
import { useEffect, useId, useRef, useState } from "react";

import { tokenThemeVariables } from "../diagrams/mermaid-theme";
import { ChatCopyButton } from "./ChatCodeBlock";

/**
 * Quotes unquoted `[...]` flowchart node labels that contain characters the
 * classic flowchart grammar cannot parse unquoted — `(`, `)`, `{`, `}` — so a
 * model-written label like `C[List locations (Exchange, OneDrive, Blob)]`
 * (a real observed failure: `Parse error ... got 'PS'` on the `(`) renders
 * instead of falling back to source. Mermaid's own fix for this is quoting
 * the label (`C["List locations (Exchange, OneDrive, Blob)"]`); this applies
 * that mechanically rather than relying on the model to always remember to.
 *
 * Deliberately narrow: only touches `ID[label]` shapes (the commonest node
 * form in model output), only when the label is not already quoted, and only
 * when it contains one of the four unparseable characters — anything else
 * (round `(...)`, diamond `{...}`, decorated shapes) is left alone rather than
 * guessed at. The `[^\]"]*` capture excludes any label already containing a
 * literal `"` from the match entirely — such a label is already ambiguous
 * (unquoted-but-quoted), so this leaves it for mermaid's own parser to reject
 * rather than guessing at an escape.
 *
 * A label starting with `[`, `(`, `/`, or `\` right after the node's opening
 * `[` is bailed out on rather than sanitized: that is the four OTHER `[...]`
 * bracket shapes mermaid overloads the same opening character for — subroutine
 * `id[[text]]`, cylinder `id[(text)]`, parallelogram `id[/text/]`, trapezoid
 * `id[\text\]`. The regex only looks for the FIRST `]`, so on a subroutine it
 * stops at the shape's own inner `]]` instead of the outer one, and on a
 * cylinder/parallelogram/trapezoid it captures the whole shape delimiter as
 * part of the "label" and silently downgrades the node to a plain rectangle
 * when it quotes it. Left untouched, these still fail the same way they did
 * before this function existed (a genuinely paren-bearing cylinder label was
 * already unparseable) — worse than not fixing it would be corrupting a shape
 * that was rendering fine.
 *
 * Applied only to the copy handed to `mermaid.parse`/`render` — the `code`
 * prop keeps the model's exact text for the copy button and the source
 * fallback, so a reader never sees text the model didn't write.
 */
export function sanitizeMermaidLabels(code: string): string {
  return code.replace(/(\b[\w-]+)\[([^\]"]*)\]/g, (whole, id: string, label: string) => {
    if (/^[[(/\\]/.test(label)) return whole;
    if (!/[(){}]/.test(label)) return whole;
    return `${id}["${label}"]`;
  });
}

/**
 * The palette table moved to `../diagrams/mermaid-theme` when the
 * architecture diagram became a second mermaid surface — one table, both
 * diagrams, so a token added for one is a token added for both.
 */

export type ChatMermaidBlockProps = {
  /** Diagram source — rendered verbatim as the no-JS / parse-failure fallback. */
  code: string;
  /** Caption language label. */
  label?: string;
  className?: string;
};

export function ChatMermaidBlock({ code, label = "mermaid", className }: ChatMermaidBlockProps) {
  const [svg, setSvg] = useState("");
  const [failed, setFailed] = useState(false);
  const [showSource, setShowSource] = useState(false);
  // Bumped by the [data-theme] observer to re-run the render effect.
  const [themeTick, setThemeTick] = useState(0);
  const hostRef = useRef<HTMLElement>(null);
  // React 19's useId is «r0»-shaped; mermaid uses this verbatim as an SVG id
  // AND inside generated CSS selectors, so strip everything non-alphanumeric.
  const id = `chat-mermaid-${useId().replace(/[^a-zA-Z0-9]/g, "")}`;

  useEffect(() => {
    const observer = new MutationObserver(() => setThemeTick((n) => n + 1));
    observer.observe(document.documentElement, {
      attributes: true,
      attributeFilter: ["data-theme"],
    });
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    const host = hostRef.current;
    if (!host) return;
    let cancelled = false;

    void (async () => {
      try {
        const mermaid = (await import("mermaid")).default;
        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: "base",
          themeVariables: tokenThemeVariables(host),
          flowchart: { htmlLabels: false, useMaxWidth: true },
          sequence: { useMaxWidth: true },
        });
        // Validate first: parse throws on a malformed graph without touching
        // the document, so the failure path never leaves stray nodes behind.
        const sanitized = sanitizeMermaidLabels(code);
        await mermaid.parse(sanitized);
        const rendered = await mermaid.render(id, sanitized);
        if (cancelled) return;
        setSvg(rendered.svg);
        setFailed(false);
      } catch {
        if (cancelled) return;
        setSvg("");
        setFailed(true);
      }
    })();

    return () => {
      cancelled = true;
    };
  }, [code, id, themeTick]);

  const drawn = Boolean(svg) && !failed;
  const cls = ["chat-md-mermaid", className ?? ""].filter(Boolean).join(" ");

  return (
    <figure
      ref={hostRef}
      className={cls}
      data-state={failed ? "source" : drawn ? "diagram" : "pending"}
    >
      <figcaption>
        <span>{failed ? `${label} · source` : label}</span>
        <span className="chat-md-mermaid-actions">
          {drawn ? (
            <button
              type="button"
              className="chat-md-copy"
              aria-expanded={showSource}
              aria-controls={`${id}-source`}
              onClick={() => setShowSource((v) => !v)}
            >
              {showSource ? "hide source" : "view source"}
            </button>
          ) : null}
          <ChatCopyButton text={code} ariaLabel="Copy diagram source" />
        </span>
      </figcaption>
      {drawn ? (
        <div
          className="chat-md-mermaid-fig"
          role="img"
          aria-label={`${label} diagram`}
          // mermaid.render returns a sanitized SVG string under
          // securityLevel: "strict" — see the module docblock.
          dangerouslySetInnerHTML={{ __html: svg }}
        />
      ) : null}
      {!drawn || showSource ? (
        <pre id={`${id}-source`}>
          <code>{code}</code>
        </pre>
      ) : null}
    </figure>
  );
}
