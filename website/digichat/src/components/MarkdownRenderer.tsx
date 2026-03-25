import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import type { Components } from "react-markdown";
import type { ReactNode } from "react";

interface CodeProps {
  className?: string;
  children?: ReactNode;
  inline?: boolean;
}

const components: Components = {
  // eslint-disable-next-line @typescript-eslint/no-explicit-any
  code: ({ className, children, ...props }: CodeProps & Record<string, any>) => {
    const match = /language-(\w+)/.exec(className ?? "");
    const lang = match?.[1];
    const isInline = props.inline as boolean | undefined;
    if (isInline) {
      return (
        <code className="font-mono text-[0.84em] bg-white/[0.07] px-1.5 py-0.5 rounded-[4px] text-[#e6e6e6]">
          {children}
        </code>
      );
    }
    return (
      <div className="my-3 rounded-lg overflow-hidden border border-[#2a2a2a]">
        {lang && (
          <div className="px-3 py-1.5 bg-white/[0.04] border-b border-[#2a2a2a] flex items-center gap-2">
            <span className="font-mono text-[0.68rem] text-[#555] uppercase tracking-widest">
              {lang}
            </span>
          </div>
        )}
        <pre className="p-3 overflow-x-auto bg-black/50 text-[0.82rem] font-mono leading-relaxed text-[#e6e6e6] m-0">
          <code>{children}</code>
        </pre>
      </div>
    );
  },
  p: ({ children }) => (
    <p className="mb-2.5 last:mb-0 text-[#e6e6e6] leading-relaxed">{children}</p>
  ),
  a: ({ href, children }) => (
    <a href={href} className="text-[#4a90e2] hover:underline" target="_blank" rel="noopener noreferrer">
      {children}
    </a>
  ),
  ul: ({ children }) => (
    <ul className="mb-2.5 pl-5 space-y-1 list-disc text-[#e6e6e6]">{children}</ul>
  ),
  ol: ({ children }) => (
    <ol className="mb-2.5 pl-5 space-y-1 list-decimal text-[#e6e6e6]">{children}</ol>
  ),
  li: ({ children }) => <li className="leading-relaxed">{children}</li>,
  blockquote: ({ children }) => (
    <blockquote className="border-l-2 border-[#2a2a2a] pl-3 my-2 text-[#a3a3a3] italic">
      {children}
    </blockquote>
  ),
  h1: ({ children }) => (
    <h1 className="text-lg font-semibold text-[#e6e6e6] mb-2 mt-3 first:mt-0 tracking-tight">
      {children}
    </h1>
  ),
  h2: ({ children }) => (
    <h2 className="text-base font-semibold text-[#e6e6e6] mb-2 mt-3 first:mt-0 tracking-tight">
      {children}
    </h2>
  ),
  h3: ({ children }) => (
    <h3 className="text-sm font-semibold text-[#e6e6e6] mb-1.5 mt-2.5 first:mt-0">
      {children}
    </h3>
  ),
  strong: ({ children }) => (
    <strong className="font-semibold text-[#e6e6e6]">{children}</strong>
  ),
  hr: () => <hr className="my-3 border-[#2a2a2a]" />,
  table: ({ children }) => (
    <div className="my-3 overflow-x-auto rounded-lg border border-[#2a2a2a]">
      <table className="w-full text-[0.82rem] text-[#e6e6e6] border-collapse">
        {children}
      </table>
    </div>
  ),
  thead: ({ children }) => (
    <thead className="bg-white/[0.04] border-b border-[#2a2a2a]">{children}</thead>
  ),
  th: ({ children }) => (
    <th className="px-3 py-2 text-left font-medium text-[#a3a3a3] text-[0.75rem] uppercase tracking-wider">
      {children}
    </th>
  ),
  td: ({ children }) => (
    <td className="px-3 py-2 border-t border-[#2a2a2a] first:border-t-0">{children}</td>
  ),
};

interface Props {
  content: string;
}

export function MarkdownRenderer({ content }: Props) {
  return (
    <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
      {content}
    </ReactMarkdown>
  );
}
