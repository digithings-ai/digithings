"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { usePathname } from "next/navigation";
import { chatFailureSentence } from "../../../../clients/digiquant-tui/src/pages/chat-format";
import { DESK_CHANGE_EVENT, DESK_STORAGE_KEY, financialDesk, financialDeskLabel, type FinancialDesk } from "./financial-desk";
import { deskPathFromPathname } from "./paths";
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
  desk: FinancialDesk;
  contextLabel: string;
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

/** Sessions and the open thread for /tools/digichat. The rail and the pane share this.
 *  `active` is false on every other desk page so the shell can stay mounted. */
export function ChatDesk({ children, active = true }: { children: ReactNode; active?: boolean }) {
  const [threads, setThreads] = useState<DeskThread[]>([]);
  const [messages, setMessages] = useState<DeskMessage[]>([]);
  const [activeId, setActiveId] = useState<string | undefined>(undefined);
  const [notice, setNotice] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [running, setRunning] = useState(false);
  const sessionRef = useRef<string | null>(null);
  const pathname = usePathname() ?? "/app";
  const [storedDesk, setStoredDesk] = useState<string | null>(null);
  const desk = financialDesk(deskPathFromPathname(pathname), storedDesk);
  const contextLabel = financialDeskLabel(desk);

  useEffect(() => {
    const read = () => {
      try {
        setStoredDesk(localStorage.getItem(DESK_STORAGE_KEY));
      } catch {
        setStoredDesk(null);
      }
    };
    read();
    window.addEventListener(DESK_CHANGE_EVENT, read);
    window.addEventListener("storage", read);
    return () => {
      window.removeEventListener(DESK_CHANGE_EVENT, read);
      window.removeEventListener("storage", read);
    };
  }, []);

  const withDesk = useCallback((route: string) => {
    const join = route.includes("?") ? "&" : "?";
    return `${route}${join}desk=${desk}`;
  }, [desk]);

  useEffect(() => {
    if (!active) return;
    const ac = new AbortController();
    let cancel = false;
    void (async () => {
      const [sessionRead, currentRead, messageRead] = await Promise.all([
        readOfficial(withDesk(CHAT_ROUTES.sessions), "fields", ac.signal),
        readOfficial(withDesk(CHAT_ROUTES.current), "fields", ac.signal),
        readOfficial(withDesk(CHAT_ROUTES.messages), "fields", ac.signal),
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
  }, [active, desk, withDesk]);

  const select = useCallback((id: string) => {
    sessionRef.current = id;
    setActiveId(id);
    void (async () => {
      const messageRead = await readOfficial(withDesk(`/chat/sessions/${encodeURIComponent(id)}/messages`), "fields");
      if (sessionRef.current !== id) return;
      if (!usable(messageRead)) {
        setMessages([]);
        setNotice(chatFailureSentence(messageRead.result.lines));
        return;
      }
      setNotice(null);
      setMessages(messageRows(messageRead.data));
    })();
  }, [withDesk]);

  const send = useCallback(async (text: string) => {
    const trimmed = text.trim();
    if (!trimmed) return;
    setRunning(true);
    try {
      let id = sessionRef.current;
      if (!id) {
        const created = await postOfficial(withDesk("/chat/sessions"), { desk });
        if (!usable(created)) {
          setNotice(chatFailureSentence(created.result.lines));
          return;
        }
        id = sessionId(created.data);
        if (!id) return;
        sessionRef.current = id;
        setActiveId(id);
        const sessionRead = await readOfficial(withDesk(CHAT_ROUTES.sessions), "fields");
        if (usable(sessionRead)) setThreads(sessionRows(sessionRead.data));
      }
      const sent = await postOfficial(withDesk(messageRoute(id)), { text: trimmed, desk });
      if (!usable(sent)) {
        setNotice(chatFailureSentence(sent.result.lines));
        return;
      }
      const reply = replyText(sent.data);
      const messageRead = await readOfficial(withDesk(messageRoute(id)), "fields");
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
  }, [desk, withDesk]);

  const value: ChatDeskValue | null = active
    ? { threads, messages, activeId, notice, ready, running, desk, contextLabel, select, send }
    : null;

  return <ChatDeskContext.Provider value={value}>{children}</ChatDeskContext.Provider>;
}
