import { useEffect, useRef, useState } from "react";
import {
  CHAT_ROUTES,
  messageRoute,
  messageRows,
  replyText,
  sessionId,
  sessionRows,
  type DeskMessage,
  type DeskThread,
} from "../../../../apps/digiquant-web/components/desk/chat-model";
import { chatFailureSentence } from "./chat-format";
import { presentResponse, type ReadResult } from "../read";
import { BG, INK, MUTE } from "../theme";

type Loaded = { result: ReadResult; data: unknown };

const WELCOME = "What should we inspect?";

function usable(result: ReadResult): boolean {
  return result.status === "ok" || result.status === "empty";
}

function dataOf(body: unknown, result: ReadResult): unknown {
  if (result.status === "error" || result.status === "stub") return null;
  if (!body || typeof body !== "object" || !("data" in body)) return null;
  return (body as { data: unknown }).data;
}

async function loadChat(api: string, route: string, signal?: AbortSignal): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return {
      result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null },
      data: null,
    };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, "fields");
  return { result, data: dataOf(body, result) };
}

async function postChat(api: string, route: string, payload: unknown): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, {
      method: "POST",
      headers: { "content-type": "application/json" },
      body: JSON.stringify(payload),
    });
  } catch {
    return {
      result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null },
      data: null,
    };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, "fields");
  return { result, data: dataOf(body, result) };
}

function bodyOf(messages: DeskMessage[], notice: string | null, ready: boolean): string {
  if (!ready) return "loading…";
  if (notice) return notice;
  if (!messages.length) return WELCOME;
  return messages.map((message) => message.content).join("\n\n");
}

/** Desk chat. Threads are drawn in the rail by the app. No second sidebar and no read footer. */
export function ChatPage({
  api,
  activeId,
  typing,
  onThreads,
  onActive,
  onTyping,
}: {
  api: string;
  activeId?: string;
  typing: boolean;
  onThreads: (threads: DeskThread[]) => void;
  onActive: (id: string | undefined) => void;
  onTyping: (on: boolean) => void;
}) {
  const [messages, setMessages] = useState<DeskMessage[]>([]);
  const [notice, setNotice] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [draft, setDraft] = useState("");
  const seen = useRef<string | undefined>(undefined);
  const sessionRef = useRef<string | null>(null);

  useEffect(() => {
    const ac = new AbortController();
    let cancel = false;
    void (async () => {
      const [sessionRead, currentRead, messageRead] = await Promise.all([
        loadChat(api, CHAT_ROUTES.sessions, ac.signal),
        loadChat(api, CHAT_ROUTES.current, ac.signal),
        loadChat(api, CHAT_ROUTES.messages, ac.signal),
      ]);
      if (cancel) return;
      const failures = [sessionRead, currentRead, messageRead].filter(
        (read) => read.result.status === "error" || read.result.status === "stub",
      );
      const sentence = chatFailureSentence(failures.flatMap((read) => read.result.lines));
      const id = usable(currentRead.result) ? sessionId(currentRead.data) : null;
      sessionRef.current = id;
      seen.current = id ?? undefined;
      setNotice(sentence);
      setMessages(usable(messageRead.result) ? messageRows(messageRead.data) : []);
      onThreads(usable(sessionRead.result) ? sessionRows(sessionRead.data) : []);
      onActive(id ?? undefined);
      setReady(true);
    })();
    return () => {
      cancel = true;
      ac.abort();
      onTyping(false);
    };
  }, [api, onActive, onThreads, onTyping]);

  useEffect(() => {
    if (!activeId || activeId === seen.current) return;
    seen.current = activeId;
    sessionRef.current = activeId;
    const ac = new AbortController();
    let cancel = false;
    void loadChat(api, `/chat/sessions/${encodeURIComponent(activeId)}/messages`, ac.signal).then((messageRead) => {
      if (cancel) return;
      if (!usable(messageRead.result)) {
        setMessages([]);
        setNotice(chatFailureSentence(messageRead.result.lines));
        return;
      }
      setNotice(null);
      setMessages(messageRows(messageRead.data));
    });
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [activeId, api]);

  const submit = (raw: string) => {
    const text = (typeof raw === "string" ? raw : draft).trim();
    if (!text || notice) return;
    setDraft("");
    void (async () => {
      let id = sessionRef.current;
      if (!id) {
        const created = await postChat(api, "/chat/sessions", {});
        if (!usable(created.result)) {
          setNotice(chatFailureSentence(created.result.lines));
          return;
        }
        id = sessionId(created.data);
        if (!id) return;
        sessionRef.current = id;
        seen.current = id;
        onActive(id);
        const sessionRead = await loadChat(api, CHAT_ROUTES.sessions);
        if (usable(sessionRead.result)) onThreads(sessionRows(sessionRead.data));
      }
      const sent = await postChat(api, messageRoute(id), { text });
      if (!usable(sent.result)) {
        setNotice(chatFailureSentence(sent.result.lines));
        return;
      }
      const reply = replyText(sent.data);
      const messageRead = await loadChat(api, messageRoute(id));
      if (!usable(messageRead.result)) {
        setNotice(chatFailureSentence(messageRead.result.lines));
        return;
      }
      const rows = messageRows(messageRead.data);
      if (rows.length > 0) setMessages(rows);
      else if (reply) {
        setMessages((prev) => [
          ...prev,
          { id: `user-${id}`, role: "user", content: text },
          { id: `reply-${id}`, role: "assistant", content: reply },
        ]);
      } else {
        setMessages((prev) => [...prev, { id: `user-${id}`, role: "user", content: text }]);
      }
      setNotice(null);
    })();
  };

  const text = bodyOf(messages, notice, ready);
  const compose = ready && !notice;

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <box flexGrow={1} paddingLeft={1} paddingRight={1} paddingTop={1}>
        <text fg={notice || !ready ? MUTE : INK}>{text}</text>
      </box>
      {compose ? (
        <box height={1} paddingLeft={1} paddingRight={1} onMouseDown={() => onTyping(true)}>
          <input
            flexGrow={1}
            focused={typing}
            value={draft}
            placeholder="Ask digichat…"
            placeholderColor={MUTE}
            backgroundColor={BG}
            textColor={INK}
            focusedBackgroundColor={BG}
            focusedTextColor={INK}
            onInput={setDraft}
            onSubmit={submit}
          />
        </box>
      ) : null}
    </box>
  );
}
