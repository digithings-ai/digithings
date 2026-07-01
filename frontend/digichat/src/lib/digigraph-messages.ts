import type { ModelMessage } from "ai";

/**
 * Mirror digigraph.models._coerce_openai_message_content so trace-path requests
 * match OpenAI-style bodies DigiGraph validates reliably.
 */
export function coerceMessageContentToString(content: unknown): string {
  if (content == null) return "";
  if (typeof content === "string") return content;
  if (Array.isArray(content)) {
    const parts: string[] = [];
    for (const block of content) {
      if (typeof block === "string") {
        parts.push(block);
        continue;
      }
      if (block && typeof block === "object" && "text" in block) {
        const text = (block as { text?: unknown }).text;
        if (typeof text === "string") parts.push(text);
      }
    }
    return parts.join("");
  }
  if (typeof content === "object" && content !== null && "text" in content) {
    const text = (content as { text?: unknown }).text;
    return typeof text === "string" ? text : "";
  }
  return String(content);
}

export function coreMessagesToDigigraphOpenAi(
  messages: ModelMessage[]
): Array<{ role: string; content: string }> {
  return messages.map((m) => ({
    role: m.role,
    content: coerceMessageContentToString(m.content),
  }));
}
