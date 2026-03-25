interface Props {
  text: string;
}

export function ThinkingBlock({ text }: Props) {
  return (
    <details className="my-2 rounded-lg border border-[#2a2a2a] bg-white/[0.025] group">
      <summary className="cursor-pointer px-3 py-2 text-[0.75rem] text-[#a3a3a3] list-none select-none flex items-center gap-1.5 group-open:text-[#e6e6e6] group-open:mb-1">
        <svg
          className="w-3 h-3 shrink-0 transition-transform group-open:rotate-90"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
        Thinking…
      </summary>
      <pre className="px-3 pb-3 text-[0.78rem] font-mono text-[#a3a3a3] whitespace-pre-wrap break-words leading-relaxed">
        {text}
      </pre>
    </details>
  );
}
