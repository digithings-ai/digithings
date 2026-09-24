"use client";

import ReactMarkdown from "react-markdown";

export function MarkdownPage({ markdown }: { markdown: string }) {
  return (
    <div className="mt-8 text-slate-800 [&_a]:text-[var(--docs-accent)] [&_a]:underline [&_blockquote]:border-l-4 [&_blockquote]:border-[var(--docs-accent-soft)] [&_blockquote]:pl-4 [&_blockquote]:text-slate-600 [&_code]:rounded [&_code]:bg-slate-100 [&_code]:px-1.5 [&_code]:py-0.5 [&_code]:font-mono [&_h2]:mt-8 [&_h2]:mb-3 [&_h2]:text-xl [&_h2]:font-semibold [&_h2]:text-slate-900 [&_h3]:mt-6 [&_h3]:mb-2 [&_h3]:text-lg [&_h3]:font-semibold [&_li]:my-1 [&_ol]:my-4 [&_ol]:list-decimal [&_ol]:pl-6 [&_p]:my-4 [&_p]:leading-7 [&_pre]:my-5 [&_pre]:overflow-x-auto [&_pre]:rounded-lg [&_pre]:bg-slate-950 [&_pre]:p-4 [&_pre_code]:bg-transparent [&_pre_code]:p-0 [&_pre_code]:text-slate-50 [&_strong]:font-semibold [&_ul]:my-4 [&_ul]:list-disc [&_ul]:pl-6">
      <ReactMarkdown>{markdown}</ReactMarkdown>
    </div>
  );
}
