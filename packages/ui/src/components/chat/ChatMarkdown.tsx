/**
 * Chat markdown — the rich-text frame for an assistant turn (#1418):
 * headings, emphasis, lists, quotes, links, tables, math and diagrams styled
 * on the token palette so rendered markdown reads as one surface with the
 * transcript. Renders a `.chat-md` scope whose ELEMENT combinators (with their
 * color-mix washes and ::marker accents) live in styles/chat-core.css —
 * markdown renderers need no per-node classes; bare tags pick up the
 * grammar, which is exactly how digichat-ui's .dc-md-* map onto it. Fenced
 * code with the copy affordance is <ChatCodeBlock>; a bare <pre> still
 * reads as the same hairline box.
 *
 * Two ways in:
 *
 *   <ChatMarkdown>{nodes}</ChatMarkdown>       frame only — static, server-safe
 *   <ChatMarkdown source={md} />               frame + renderer
 *
 * `source` runs the shared pipeline in <ChatMarkdownSource>: GFM, `$inline$` /
 * `$$block$$` math via remark-math + rehype-katex (rendered at parse time, so
 * it survives with JS off), and ```mermaid fences via <ChatMermaidBlock>
 * (client-only, lazily imported, source shown until it draws). Both may be
 * combined — `source` renders first, then children, which is how a streaming
 * turn pins <ChatStreamCursor> to the end of the text.
 *
 * The children-only path stays directive-free and server-safe.
 *
 * It does NOT, however, avoid the cost: `ChatMarkdownSource` is a **static**
 * import below, so react-markdown, remark-gfm, remark-math, rehype-katex (→ katex,
 * 266 KB raw / 76 KB gzipped) and <ChatMermaidBlock> are in the module graph of
 * every consumer, including one that only ever passes children. An earlier version
 * of this comment claimed "passing `source` pulls in the client renderer", implying
 * the children path escaped it; that was wrong. Only `mermaid` itself (~2.9 MB) is
 * genuinely deferred, via `await import("mermaid")` inside the effect.
 *
 * Making the whole renderer dynamic would be the real fix and is not done here: it
 * would turn every `source` render into a suspense boundary and change the
 * streaming behaviour, which needs its own change with its own review.
 */
import type { ReactNode } from "react";

import { ChatMarkdownSource, type CodeBlockOverride } from "./ChatMarkdownSource";

export type { CodeBlockOverride } from "./ChatMarkdownSource";

export type ChatMarkdownProps = {
  children?: ReactNode;
  /** Markdown source — GFM + `$math$` + ```mermaid, rendered by the shared pipeline. */
  source?: string;
  className?: string;
  /** Per-fence-language block-code hook — see {@link CodeBlockOverride}. Only
   * consulted when `source` is passed; the children-only frame has nothing to
   * parse. Optional, and additive: omit it and every fence renders exactly as
   * before (mermaid diagram, or the copy-caption code block). */
  renderCodeBlock?: CodeBlockOverride;
};

export function ChatMarkdown({ children, source, className, renderCodeBlock }: ChatMarkdownProps) {
  const cls = ["chat-md min-w-0 text-[0.88rem] leading-[1.6]", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      {source ? <ChatMarkdownSource source={source} renderCodeBlock={renderCodeBlock} /> : null}
      {children}
    </div>
  );
}
