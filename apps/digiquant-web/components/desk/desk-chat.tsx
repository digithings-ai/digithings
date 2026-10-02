"use client";

import { useEffect, useRef, useState } from "react";
import { AssistantRuntimeProvider, useExternalStoreRuntime } from "@assistant-ui/react";
import { DigichatThread } from "@digithings/ui/chat/thread";
import { DigichatThreadList } from "@digithings/ui/chat/thread-list";
import { DASH } from "../../../../clients/digiquant-tui/src/read";
import type { ReadResult } from "../../../../clients/digiquant-tui/src/read";
import { DeskFrame } from "./desk-frame";
import {
  CHAT_ROUTES,
  messageRoute,
  messageRows,
  replyText,
  sessionId,
  sessionRows,
  type DeskMessage,
} from "./chat-model";
import { postOfficial, readOfficial, type OfficialRead } from "./read-block";

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

function lineOf(read: OfficialRead | null): string {
  if (!read) return "loading…";
  return read.result.lines.join("\n") || DASH;
}

function ReadBlock({ label, route, read }: { label: string; route: string; read: OfficialRead | null }) {
  const status = read?.result.status ?? "loading";
  return (
    <section aria-label={label} className="min-w-0 border-r border-hair px-2 py-1 last:border-r-0">
      <h2 className="m-0 truncate text-[0.65rem] font-normal text-ink-mute">{label}</h2>
      <p className={`m-0 max-h-16 overflow-auto whitespace-pre-wrap text-[0.7rem] ${tone[status]}`}>{lineOf(read)}</p>
      <p className="m-0 truncate text-[0.6rem] text-ink-mute">{route}</p>
    </section>
  );
}

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

/** The digichat thread and sidebar. Reads and sends go to the official API. No script. */
export function DeskChat() {
  const [sessions, setSessions] = useState<OfficialRead | null>(null);
  const [current, setCurrent] = useState<OfficialRead | null>(null);
  const [transcript, setTranscript] = useState<OfficialRead | null>(null);
  const [messages, setMessages] = useState<DeskMessage[]>([]);
  const [activeId, setActiveId] = useState<string | undefined>(undefined);
  const [running, setRunning] = useState(false);
  const [sendNote, setSendNote] = useState("");
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    let cancel = false;
    void (async () => {
      const [sessionRead, currentRead, messageRead] = await Promise.all([
        readOfficial(CHAT_ROUTES.sessions, "fields", ac.signal),
        readOfficial(CHAT_ROUTES.current, "fields", ac.signal),
        readOfficial(CHAT_ROUTES.messages, "fields", ac.signal),
      ]);
      if (cancel) return;
      setSessions(sessionRead);
      setCurrent(currentRead);
      setTranscript(messageRead);
      const usable = messageRead.result.status === "ok" || messageRead.result.status === "empty";
      setMessages(usable ? messageRows(messageRead.data) : []);
      const id =
        currentRead.result.status === "ok" || currentRead.result.status === "empty" ? sessionId(currentRead.data) : null;
      sessionRef.current = id;
      setActiveId(id ?? undefined);
    })();
    return () => {
      cancel = true;
      ac.abort();
    };
  }, []);

  const threads =
    sessions && (sessions.result.status === "ok" || sessions.result.status === "empty") ? sessionRows(sessions.data) : [];
  const failed = [sessions, current, transcript].some(
    (read) => read != null && (read.result.status === "error" || read.result.status === "stub"),
  );
  const settled = sessions != null && current != null && transcript != null;

  const runtime = useExternalStoreRuntime({
    messages,
    isRunning: running,
    convertMessage: (message) => message,
    onNew: async (message) => {
      const text = appendText(message);
      if (!text) {
        setSendNote(DASH);
        return;
      }
      setRunning(true);
      setSendNote("loading…");
      try {
        let id = sessionRef.current;
        if (!id) {
          const created = await postOfficial("/chat/sessions", {});
          setSendNote(lineOf(created));
          if (created.result.status !== "ok" && created.result.status !== "empty") return;
          id = sessionId(created.data);
          if (!id) return;
          sessionRef.current = id;
          setActiveId(id);
        }
        const sent = await postOfficial(messageRoute(id), { text });
        setSendNote(lineOf(sent));
        if (sent.result.status !== "ok" && sent.result.status !== "empty") return;
        const reply = replyText(sent.data);
        if (!reply) return;
        setMessages((prev) => [...prev, { id: `reply-${id}`, role: "assistant", content: reply }]);
      } finally {
        setRunning(false);
      }
    },
    adapters: {
      threadList: {
        threadId: activeId,
        threads,
        onSwitchToNewThread: async () => {
          setRunning(true);
          setSendNote("loading…");
          try {
            const created = await postOfficial("/chat/sessions", {});
            setSendNote(lineOf(created));
            const id = sessionId(created.data);
            if (!id) return;
            sessionRef.current = id;
            setActiveId(id);
          } finally {
            setRunning(false);
          }
        },
        onSwitchToThread: async (id: string) => {
          sessionRef.current = id;
          setActiveId(id);
          const [currentRead, messageRead] = await Promise.all([
            readOfficial(`/chat/sessions/${encodeURIComponent(id)}`, "fields"),
            readOfficial(`/chat/sessions/${encodeURIComponent(id)}/messages`, "fields"),
          ]);
          setCurrent(currentRead);
          setTranscript(messageRead);
          const usable = messageRead.result.status === "ok" || messageRead.result.status === "empty";
          setMessages(usable ? messageRows(messageRead.data) : []);
        },
      },
    },
  });

  return (
    <DeskFrame current="/tools/chat">
      <AssistantRuntimeProvider runtime={runtime}>
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="grid min-h-0 flex-1 grid-cols-[14rem_minmax(0,1fr)]">
            <DigichatThreadList className="h-full min-h-0" />
            <div className="flex min-h-0 flex-col">
              {sendNote ? (
                <p role="status" className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.7rem] text-ink-soft">
                  {sendNote}
                </p>
              ) : null}
              <DigichatThread
                welcome={settled && !failed ? "What should we inspect?" : ""}
                placeholder="Ask digichat…"
                className="min-h-0 flex-1"
              />
            </div>
          </div>
          <div className="grid shrink-0 grid-cols-3 border-t border-hair">
            <ReadBlock label="Chat · sessions" route={CHAT_ROUTES.sessions} read={sessions} />
            <ReadBlock label="Chat · thread" route={CHAT_ROUTES.current} read={current} />
            <ReadBlock label="Chat · transcript" route={CHAT_ROUTES.messages} read={transcript} />
          </div>
        </div>
      </AssistantRuntimeProvider>
    </DeskFrame>
  );
}
