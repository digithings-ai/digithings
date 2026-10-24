import type { ChatModelAdapter, ThreadMessageLike } from "@assistant-ui/react";
import { AssistantRuntimeProvider, useLocalRuntime } from "@assistant-ui/react";
import { createRoot } from "react-dom/client";
import { DigichatThread } from "../src/components/chat/DigichatThread";

const adapter: ChatModelAdapter = { async run() { return { content: [{ type: "text", text: "ok" }] }; } };
const TRACE: ThreadMessageLike[] = [
  { role: "user", content: [{ type: "text", text: "Look up both notes." }] },
  { role: "assistant", content: [
    { type: "reasoning", text: "Checking both tools before answering." },
    { type: "tool-call", toolCallId: "t1", toolName: "digisearch", argsText: "{\"q\":\"notes\"}", result: "ok" },
    { type: "tool-call", toolCallId: "t2", toolName: "digivault_search_notes", argsText: "{}", result: "ok" },
    { type: "text", text: "Both lookups landed." },
  ] },
];
function Harness() {
  const runtime = useLocalRuntime(adapter, { initialMessages: TRACE });
  return (<AssistantRuntimeProvider runtime={runtime}><div style={{ height: "100vh" }}><DigichatThread placeholder="Ask digichat…" /></div></AssistantRuntimeProvider>);
}
createRoot(document.getElementById("root")!).render(<Harness />);
