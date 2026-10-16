import type { UIMessage } from "ai";

/**
 * Chat-shaped `{ role, content }` pairs for text-only upstream protocols
 * (LangGraph, AG-UI, A2A — #4543). Empty messages are dropped.
 */
export function toChatMessages(
  messages: UIMessage[],
): Array<{ role: string; content: string }> {
  return messages
    .map((m) => ({
      role: m.role,
      content: m.parts
        .filter((p): p is { type: "text"; text: string } => p.type === "text")
        .map((p) => p.text)
        .join("\n")
        .trim(),
    }))
    .filter((m) => m.content.length > 0);
}

/** Last user text parts joined — shared by Foundry (and any future) adapters. */
export function lastUserMessageText(messages: UIMessage[]): string {
  for (let i = messages.length - 1; i >= 0; i--) {
    const m = messages[i];
    if (m.role !== "user") continue;
    return m.parts
      .filter((p): p is { type: "text"; text: string } => p.type === "text")
      .map((p) => p.text)
      .join("\n")
      .trim();
  }
  return "";
}
