"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { chatFailureSentence } from "../../../../clients/digiquant-tui/src/pages/chat-format";
import {
  CHAT_ROUTES,
  messageRoute,
  messageRows,
  replyText,
  sessionId,
  sessionRows,
  type DeskMessage,
  type DeskThread,
} from "./chat-model";
import { postOfficial, readOfficial, type OfficialRead } from "./read-block";

type ChatDeskValue = {
  threads: DeskThread[];
  messages: DeskMessage[];
  activeId?: string;
  notice: string | null;
  ready: boolean;
  running: boolean;
  select: (id: string) => void;
  send: (text: string) => Promise<void>;
};

const ChatDeskContext = createContext<ChatDeskValue | null>(null);

export function useChatDesk(): ChatDeskValue | null {
  return useContext(ChatDeskContext);
}

function failed(read: OfficialRead): boolean {
  return read.result.status === "error" || read.result.status === "stub";
}

function usable(read: OfficialRead): boolean {
  return read.result.status === "ok" || read.result.status === "empty";
}

/** Sessions and the open thread for /tools/chat. The rail and the pane share this. */
export function ChatDesk({ children }: { children: ReactNode }) {
  const [threads, setThreads] = useState<DeskThread[]>([]);
  const [messages, setMessages] = useState<DeskMessage[]>([]);
  const [activeId, setActiveId] = useState<string | undefined>(undefined);
  const [notice, setNotice] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(false);
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
      const failures = [sessionRead, currentRead, messageRead].filter(failed);
      setNotice(chatFailureSentence(failures.flatMap((read) => read.result.lines)));
      setThreads(usable(sessionRead) ? sessionRows(sessionRead.data) : []);
      setMessages(usable(messageRead) ? messageRows(messageRead.data) : []);
      const id = usable(currentRead) ? sessionId(currentRead.data) : null;
      sessionRef.current = id;
      setActiveId(id ?? undefined);
      setReady(true);
    })();
    return () => {
      cancel = true;
      ac.abort();
    };
  }, []);

  const select = useCallback((id: string) => {
    sessionRef.current = id;
    setActiveId(id);
    void (async () => {
      const messageRead = await readOfficial(`/chat/sessions/${encodeURIComponent(id)}/messages`, "fields");
      if (sessionRef.current !== id) return;
      if (!usable(messageRead)) {
        setMessages([]);
        setNotice(chatFailureSentence(messageRead.result.lines));
        return;
      }
      setNotice(null);
      setMessages(messageRows(messageRead.data));
    })();
  }, []);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setRunning(true);
    try {
      let id = sessionRef.current;
      if (!id) {
        const created = await postOfficial("/chat/sessions", {});
        if (!usable(created)) {
          setNotice(chatFailureSentence(created.result.lines));
          return;
        }
        id = sessionId(created.data);
        if (!id) return;
        sessionRef.current = id;
        setActiveId(id);
        const sessionRead = await readOfficial(CHAT_ROUTES.sessions, "fields");
        if (usable(sessionRead)) setThreads(sessionRows(sessionRead.data));
      }
      const sent = await postOfficial(messageRoute(id), { text: trimmed });
      if (!usable(sent)) {
        setNotice(chatFailureSentence(sent.result.lines));
        return;
      }
      const reply = replyText(sent.data);
      const messageRead = await readOfficial(messageRoute(id), "fields");
      if (!usable(messageRead)) {
        setNotice(chatFailureSentence(messageRead.result.lines));
        return;
      }
      const rows = messageRows(messageRead.data);
      if (rows.length > 0) setMessages(rows);
      else if (reply) {
        setMessages((prev) => [
          ...prev,
          { id: `user-${id}`, role: "user", content: trimmed },
          { id: `reply-${id}`, role: "assistant", content: reply },
        ]);
      } else {
        setMessages((prev) => [...prev, { id: `user-${id}`, role: "user", content: trimmed }]);
      }
      setNotice(null);
    } finally {
      setRunning(false);
    }
  }, []);

  return (
    <ChatDeskContext.Provider value={{ threads, messages, activeId, notice, ready, running, select, send }}>
      {children}
    </ChatDeskContext.Provider>
  );
}
