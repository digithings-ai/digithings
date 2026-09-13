"use client";

import { ChatMarkdown } from "@digithings/web";
import ReactMarkdown from "react-markdown";
import rehypeSanitize from "rehype-sanitize";
import remarkGfm from "remark-gfm";

type SafeMarkdownProps = {
  children: string;
  className?: string;
};

/**
 * Markdown renderer with rehype-sanitize (REM-076) — the parser + sanitizer
 * here are the security boundary and MUST remain the renderer. Passing
 * `children`, as below, keeps <ChatMarkdown> a styling shell: it scopes the
 * canonical `.chat-md` typography (chat-core.css) around already-sanitized
 * output. react-markdown emits bare elements with no wrapper of its own, so the
 * .chat-md child combinators (`> pre`, first/last margin trims) apply directly.
 *
 * DO NOT switch this to <ChatMarkdown source={…}>. Since #1941 that prop makes
 * <ChatMarkdown> a parser in its own right (react-markdown + remark-gfm +
 * remark-math + rehype-katex), and it carries **no rehype-sanitize** — so using
 * it here would silently route dashboard's markdown around REM-076. The comment
 * this replaced said <ChatMarkdown> had "no parser, no sanitizer" full stop,
 * which stopped being true when `source` landed.
 */
export function SafeMarkdown({ children, className }: SafeMarkdownProps) {
  return (
    <ChatMarkdown className={className}>
      <ReactMarkdown remarkPlugins={[remarkGfm]} rehypePlugins={[rehypeSanitize]}>
        {children}
      </ReactMarkdown>
    </ChatMarkdown>
  );
}
