import { ChatMarkdown } from "@digithings/ui";

/**
 * Thin delegate to `@digithings/ui` `ChatMarkdown` (`.chat-md`).
 * An edit here lands on digichat `/embed` and digithings.ai/chat together.
 */
export function MiniMarkdown({ text }: { text: string }) {
  return <ChatMarkdown source={text} />;
}
