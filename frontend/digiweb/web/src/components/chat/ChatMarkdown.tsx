/**
 * Chat markdown — the rich-text frame for an assistant turn (#1418):
 * headings, emphasis, lists, quotes, links, and tables styled on the token
 * palette so rendered markdown reads as one surface with the transcript.
 * Renders a `.chat-md` scope whose ELEMENT combinators (with their
 * color-mix washes and ::marker accents) live in styles/chat-core.css —
 * markdown renderers need no per-node classes; bare tags pick up the
 * grammar, which is exactly how digichat-ui's .dc-md-* map onto it. Fenced
 * code with the copy affordance is <ChatCodeBlock>; a bare <pre> still
 * reads as the same hairline box. Static frame, server-safe.
 */
import type { ReactNode } from "react";

export type ChatMarkdownProps = {
  children?: ReactNode;
  className?: string;
};

export function ChatMarkdown({ children, className }: ChatMarkdownProps) {
  const cls = ["chat-md min-w-0 text-[0.88rem] leading-[1.6]", className ?? ""]
    .filter(Boolean)
    .join(" ");
  return <div className={cls}>{children}</div>;
}
