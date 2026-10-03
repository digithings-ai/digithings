"use client";

import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { DigichatThread } from "@digithings/ui/chat/thread";
import { DeskFrame } from "./desk-frame";
import { ChatDesk, useChatDesk } from "./chat-desk";
import styles from "./desk-chat.module.css";

const SENTENCE = "m-0 px-3 py-6 font-mono text-[0.75rem] leading-[1.45] text-ink-mute";

function appendText(message: { content?: unknown }): string {
  const content = message.content;
  if (typeof content === "string") return content.trim();
  if (!Array.isArray(content)) return "";
  return content
    .map((part) => {
      if (!part || typeof part !== "object" || !("text" in part)) return "";
      const text = (part as { text?: unknown }).text;
      return typeof text === "string" ? text : "";
    })
    .join("")
    .trim();
}

/** Thread and composer on the desk ground. Threads live in the desk rail. */
function ChatPane() {
  const chat = useChatDesk();
  const runtime = useExternalStoreRuntime({
    messages: chat?.messages ?? [],
    isRunning: chat?.running ?? false,
    convertMessage: (message) => message,
    onNew: async (message) => {
      const text = appendText(message);
      if (!text || !chat) return;
      await chat.send(text);
    },
  });

  if (!chat?.ready) return <p className={SENTENCE}>loading…</p>;
  if (chat.notice) return <p className={SENTENCE}>{chat.notice}</p>;

  return (
    <AssistantRuntimeProvider runtime={runtime}>
      <div className={styles.ground}>
        <DigichatThread welcome="What should we inspect?" placeholder="Ask digichat…" className="min-h-0 flex-1" />
      </div>
    </AssistantRuntimeProvider>
  );
}

/** digichat on the desk. Reads and sends go to the official API. No script. */
export function DeskChat() {
  return (
    <ChatDesk>
      <DeskFrame current="/tools/chat">
        <ChatPane />
      </DeskFrame>
    </ChatDesk>
  );
}
