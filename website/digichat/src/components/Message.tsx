import { MarkdownRenderer } from "./MarkdownRenderer";
import { ThinkingBlock } from "./ThinkingBlock";
import { ToolCard } from "./ToolCard";
import { ChatMessage } from "../types";

interface Segment {
  type: "md" | "think" | "tool";
  text: string;
}

function parseSegments(raw: string): Segment[] {
  const segments: Segment[] = [];
  // Match thinking blocks: <think> (Ollama/qwen3), <thinking> (OpenWebUI/DigiGraph),
  // and tool call blocks: <tool_call>, <tool>
  const re = /<(think|thinking|tool_call|tool)>([\s\S]*?)<\/\1>/gi;
  let last = 0;
  let m: RegExpExecArray | null;
  while ((m = re.exec(raw)) !== null) {
    if (m.index > last)
      segments.push({ type: "md", text: raw.slice(last, m.index) });
    const tag = m[1]!.toLowerCase();
    segments.push({
      type: tag === "think" || tag === "thinking" ? "think" : "tool",
      text: m[2]!.trim(),
    });
    last = re.lastIndex;
  }
  if (last < raw.length) segments.push({ type: "md", text: raw.slice(last) });
  if (!segments.length) segments.push({ type: "md", text: raw });
  return segments;
}

interface Props {
  message: ChatMessage;
}

export function Message({ message }: Props) {
  const { role, content, streaming, error } = message;

  if (role === "user") {
    return (
      <div className="flex justify-end animate-[msg-in_0.4s_cubic-bezier(0.2,0.8,0.2,1)_both]">
        <div className="max-w-[min(82%,580px)] px-4 py-3 rounded-2xl rounded-br-md bg-white/[0.08] border border-white/[0.1] text-[0.9rem] leading-relaxed text-[#e6e6e6] break-words">
          <MarkdownRenderer content={content} />
        </div>
      </div>
    );
  }

  // Assistant message
  if (error) {
    return (
      <div className="flex justify-start animate-[msg-in_0.4s_cubic-bezier(0.2,0.8,0.2,1)_both]">
        <div className="max-w-[min(88%,640px)] pl-3 border-l-2 border-[#ff5f56]/40 text-[0.9rem] leading-relaxed text-[#a3a3a3] break-words">
          <p className="text-[#ff5f56] font-medium mb-1 text-[0.82rem]">Request failed</p>
          <pre className="text-[0.78rem] font-mono text-[#a3a3a3] whitespace-pre-wrap break-words">
            {content}
          </pre>
        </div>
      </div>
    );
  }

  const segments = parseSegments(content);

  return (
    <div className="flex justify-start animate-[msg-in_0.4s_cubic-bezier(0.2,0.8,0.2,1)_both]">
      <div className="max-w-[min(88%,680px)] pl-3 border-l-2 border-white/[0.08] text-[0.9rem] leading-relaxed break-words w-full">
        {segments.map((seg, i) => {
          if (seg.type === "think") return <ThinkingBlock key={i} text={seg.text} />;
          if (seg.type === "tool") return <ToolCard key={i} raw={seg.text} />;
          if (!seg.text.trim()) return null;
          return (
            <div key={i}>
              <MarkdownRenderer content={seg.text.trim()} />
            </div>
          );
        })}
        {streaming && (
          <span
            className="inline-block w-[2px] h-[1em] bg-[#4a90e2] ml-0.5 align-middle animate-[blink-cursor_0.9s_step-end_infinite]"
            aria-hidden="true"
          />
        )}
        {streaming && !content && (
          <span className="text-[#555] text-[0.82rem]">Thinking…</span>
        )}
      </div>
    </div>
  );
}
