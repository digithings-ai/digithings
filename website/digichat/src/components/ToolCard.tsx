interface Props {
  raw: string;
}

export function ToolCard({ raw }: Props) {
  // Try to parse as JSON for pretty display; fall back to raw text
  let display = raw;
  try {
    display = JSON.stringify(JSON.parse(raw), null, 2);
  } catch {
    /* keep raw */
  }

  // Try to extract a tool name from JSON
  let toolName = "tool";
  try {
    const obj = JSON.parse(raw) as Record<string, unknown>;
    if (typeof obj.name === "string") toolName = obj.name;
    else if (typeof obj.tool === "string") toolName = obj.tool;
  } catch {
    /* keep default */
  }

  return (
    <details className="my-2 rounded-lg border-l-2 border-[#ffbd2e]/50 border border-[#2a2a2a] bg-[#ffbd2e]/[0.04] group">
      <summary className="cursor-pointer px-3 py-2 text-[0.75rem] text-[#a3a3a3] list-none select-none flex items-center gap-1.5 group-open:text-[#e6e6e6] group-open:mb-1">
        <span className="text-[#ffbd2e] text-[0.8rem]">⚙</span>
        <span className="font-mono">{toolName}</span>
        <svg
          className="w-3 h-3 shrink-0 ml-auto transition-transform group-open:rotate-90"
          viewBox="0 0 16 16"
          fill="currentColor"
        >
          <path d="M6 4l4 4-4 4" stroke="currentColor" strokeWidth="1.5" fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </summary>
      <pre className="px-3 pb-3 text-[0.74rem] font-mono text-[#a3a3a3] whitespace-pre-wrap break-words leading-relaxed max-h-60 overflow-auto">
        {display}
      </pre>
    </details>
  );
}
