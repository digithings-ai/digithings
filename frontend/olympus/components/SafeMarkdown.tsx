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
 * here are the security boundary and MUST remain the renderer. The shared
 * <ChatMarkdown> wrapper is a styling shell only (no parser, no sanitizer):
 * it scopes the canonical `.chat-md` typography (chat-core.css) around the
 * sanitized output. react-markdown emits bare elements with no wrapper of
 * its own, so the .chat-md child combinators (`> pre`, first/last margin
 * trims) apply directly to the rendered markdown.
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
