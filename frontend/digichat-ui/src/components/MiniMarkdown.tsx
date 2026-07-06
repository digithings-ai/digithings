"use client";

import type { Components } from "react-markdown";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { CopyButton } from "./CopyButton";
import { MermaidBlock } from "./MermaidBlock";

const components: Components = {
  p: ({ children }) => <p className="dc-md-p">{children}</p>,
  a: ({ href, children }) => {
    const safe =
      href && (href.startsWith("https://") || href.startsWith("http://")) ? href : undefined;
    if (!safe) return <span>{children}</span>;
    return (
      <a href={safe} target="_blank" rel="noopener noreferrer">
        {children}
      </a>
    );
  },
  ul: ({ children }) => <ul className="dc-md-ul">{children}</ul>,
  ol: ({ children }) => <ol className="dc-md-ol">{children}</ol>,
  li: ({ children }) => <li className="dc-md-li">{children}</li>,
  blockquote: ({ children }) => <blockquote className="dc-md-quote">{children}</blockquote>,
  h1: ({ children }) => <h3 className="dc-md-h">{children}</h3>,
  h2: ({ children }) => <h4 className="dc-md-h">{children}</h4>,
  h3: ({ children }) => <h5 className="dc-md-h">{children}</h5>,
  h4: ({ children }) => <h6 className="dc-md-h">{children}</h6>,
  hr: () => <hr className="dc-md-hr" />,
  table: ({ children }) => (
    <div className="dc-md-table-wrap">
      <table className="dc-md-table">{children}</table>
    </div>
  ),
  thead: ({ children }) => <thead>{children}</thead>,
  tbody: ({ children }) => <tbody>{children}</tbody>,
  tr: ({ children }) => <tr>{children}</tr>,
  th: ({ children }) => <th>{children}</th>,
  td: ({ children }) => <td>{children}</td>,
  code: ({ className, children }) => {
    const raw = String(children).replace(/\n$/, "");
    const lang = className?.replace(/^language-/, "").toLowerCase() ?? "";
    if (lang === "mermaid") return <MermaidBlock code={raw} />;
    const inline = !className && !raw.includes("\n");
    if (inline) return <code className="dc-code-inline">{raw}</code>;
    return (
      <div className="dc-code-block">
        <CopyButton text={raw} className="dc-code-copy" ariaLabel="Copy code" />
        <pre>
          <code>{raw}</code>
        </pre>
      </div>
    );
  },
  pre: ({ children }) => <>{children}</>,
};

export function MiniMarkdown({ text }: { text: string }) {
  return (
    <div className="dc-md">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
}
