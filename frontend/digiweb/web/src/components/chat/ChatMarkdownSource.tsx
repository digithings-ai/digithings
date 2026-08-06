"use client";
/**
 * The parse half of <ChatMarkdown>: a markdown *string* → the `.chat-md`
 * element grammar. <ChatMarkdown> stays a directive-free, server-safe frame
 * around pre-built children; this file is where the renderer lives, split out
 * purely for the RSC boundary — react-markdown imports React hooks, so it
 * cannot be pulled into a server component.
 *
 * Pipeline (remark → rehype → React, no raw HTML anywhere — React escapes text
 * nodes and no rehype-raw is in the chain):
 *   remark-gfm    tables, task lists, strikethrough, autolinks
 *   remark-math   `$inline$` and `$$block$$` → math nodes
 *   rehype-katex  math nodes → KaTeX HTML + MathML, *at parse time*
 *
 * Math is deliberately NOT a client-side pass: rehype-katex runs inside the
 * unified pipeline, so the server markup already contains laid-out KaTeX and
 * math reads correctly with JS disabled. Only mermaid — which needs a live DOM
 * to measure text — defers to the client, and <ChatMermaidBlock> ships the
 * diagram source as its own fallback for that window.
 *
 * Emits bare tags wherever chat-core.css already has a combinator, and reaches
 * for a component only where an affordance is needed: fenced code gets
 * <ChatCodeBlock>'s copy caption, a ```mermaid fence gets <ChatMermaidBlock>.
 */
import type { Components, Options } from "react-markdown";
import ReactMarkdown from "react-markdown";
import rehypeKatex from "rehype-katex";
import remarkGfm from "remark-gfm";
import remarkMath from "remark-math";

import { ChatCodeBlock } from "./ChatCodeBlock";
import { ChatMermaidBlock } from "./ChatMermaidBlock";

/** Minimal shape of the mdast nodes remarkDisplayDollars touches. */
type MathNode = {
  type: string;
  children?: MathNode[];
  position?: { start?: { offset?: number } };
  data?: { hProperties?: { className?: string[] } };
};

/**
 * remark-math's *flow* (display) construct needs the `$$` fences on lines of
 * their own; `$$x$$` written on a single line therefore comes out as an
 * `inlineMath` node and renders squeezed inline. Models write display math on
 * one line constantly, so promote the double-dollar case: rehype-katex keys
 * displayMode off the `math-display` class alone, so swapping the class is the
 * whole fix. Single-dollar `$x$` is untouched and stays inline.
 */
function remarkDisplayDollars() {
  return (tree: unknown, file: { value?: unknown }) => {
    const src = String(file.value ?? "");
    const walk = (node: MathNode): void => {
      if (node.type === "inlineMath" && node.data?.hProperties) {
        const at = node.position?.start?.offset;
        if (typeof at === "number" && src.startsWith("$$", at)) {
          node.data.hProperties.className = ["language-math", "math-display"];
        }
      }
      for (const child of node.children ?? []) walk(child);
    };
    walk(tree as MathNode);
  };
}

const remarkPlugins: Options["remarkPlugins"] = [remarkGfm, remarkMath, remarkDisplayDollars];

/**
 * KaTeX options. `strict: "ignore"` keeps half-typed model output from filling
 * the console with parse complaints. rehype-katex forces `throwOnError` itself
 * (first strict, then a lenient retry, then a `.katex-error` span), and that
 * last-resort span is inline-styled from `errorColor` — so it is handed a
 * var() and the failed expression reads on the token palette in both themes
 * instead of KaTeX's hard-coded red.
 */
const rehypePlugins: Options["rehypePlugins"] = [
  [rehypeKatex, { strict: "ignore", errorColor: "var(--down)" }],
];

/** Only http(s) links survive; anything else (javascript:, data:) renders as text. */
function safeHref(href: string | undefined): string | undefined {
  return href && (href.startsWith("https://") || href.startsWith("http://")) ? href : undefined;
}

const components: Components = {
  a: ({ href, children }) => {
    const safe = safeHref(href);
    if (!safe) return <span>{children}</span>;
    return (
      <a href={safe} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  // Headings are downshifted two levels: a model that opens an answer with `#`
  // must not take the page's <h1>. Neither digichat /embed nor digithings.ai/chat
  // has an <h1> of its own on the transcript route, so an un-downshifted h1 from
  // streamed text becomes the document's top-level heading — a real outline and
  // screen-reader defect, not a cosmetic one. The renderer this replaced
  // (digichat-ui's MiniMarkdown) mapped h1→h3, h2→h4, h3→h5, h4→h6; that
  // behaviour is preserved here rather than dropped.
  h1: ({ children }) => <h3>{children}</h3>,
  h2: ({ children }) => <h4>{children}</h4>,
  h3: ({ children }) => <h5>{children}</h5>,
  h4: ({ children }) => <h6>{children}</h6>,
  // Tables scroll inside their own box rather than widening the turn.
  table: ({ children }) => (
    <div className="chat-md-table">
      <table>{children}</table>
    </div>
  ),
  // <ChatCodeBlock>/<ChatMermaidBlock> are <figure>s that bring their own
  // <pre>, so the fence's wrapper is dropped and `code` decides the shape.
  pre: ({ children }) => <>{children}</>,
  code: ({ className, children }) => {
    const raw = String(children).replace(/\n$/, "");
    const lang = className?.replace(/^language-/, "").toLowerCase() ?? "";
    if (lang === "mermaid") return <ChatMermaidBlock code={raw} />;
    // react-markdown ≥9 dropped the `inline` prop: a fence either carries a
    // language class or spans lines — everything else is inline `code`.
    if (!lang && !raw.includes("\n")) return <code>{raw}</code>;
    return <ChatCodeBlock code={raw} lang={lang || undefined} />;
  },
};

export type ChatMarkdownSourceProps = {
  /** Markdown source. */
  source: string;
};

export function ChatMarkdownSource({ source }: ChatMarkdownSourceProps) {
  return (
    <ReactMarkdown
      remarkPlugins={remarkPlugins}
      rehypePlugins={rehypePlugins}
      components={components}
    >
      {source}
    </ReactMarkdown>
  );
}
