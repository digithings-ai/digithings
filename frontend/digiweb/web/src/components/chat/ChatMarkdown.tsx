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
 * The children-only path stays directive-free and server-safe; passing
 * `source` pulls in the client renderer.
 */
import type { ReactNode } from "react";

import { ChatMarkdownSource } from "./ChatMarkdownSource";

export type ChatMarkdownProps = {
  children?: ReactNode;
  /** Markdown source — GFM + `$math$` + ```mermaid, rendered by the shared pipeline. */
  source?: string;
  className?: string;
};

export function ChatMarkdown({ children, source, className }: ChatMarkdownProps) {
  const cls = ["chat-md min-w-0 text-[0.88rem] leading-[1.6]", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return (
    <div className={cls}>
      {source ? <ChatMarkdownSource source={source} /> : null}
      {children}
    </div>
  );
}
