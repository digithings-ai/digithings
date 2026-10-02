import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import {
  CREDIT,
  DASH,
  PLACEHOLDER,
  ROUTES,
  UNREACHABLE,
  WELCOME,
  assembleScreen,
  messageRoute,
  postRoute,
  readRoute,
  replyText,
  sessionId,
  sessionRoute,
  type ChatMessage,
  type ChatScreen,
} from "./read";
import { ATTACH, BG, FILL, HAIR, INK, MUTE, NEW_CHAT, SEND, SOFT, USER_MARK } from "./theme";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

type Key = { name?: string; ctrl?: boolean; sequence?: string };

const blank = (note: string, status: ChatScreen["status"]): ChatScreen => ({
  status,
  sessions: [],
  currentId: null,
  messages: [],
  note,
  welcome: false,
});

function wrap(text: string, width: number): string[] {
  const limit = Math.max(8, width);
  const lines: string[] = [];
  for (const raw of text.split("\n")) {
    let rest = raw;
    if (rest.length === 0) {
      lines.push("");
      continue;
    }
    while (rest.length > limit) {
      let cut = rest.lastIndexOf(" ", limit);
      if (cut < 8) cut = limit;
      lines.push(rest.slice(0, cut));
      rest = rest.slice(cut).trimStart();
    }
    lines.push(rest);
  }
  return lines;
}

function clip(text: string, width: number): string {
  if (text.length <= width) return text;
  if (width <= 1) return "…";
  return `${text.slice(0, width - 1)}…`;
}

function center(text: string, width: number): string {
  if (text.length >= width) return text;
  const pad = Math.floor((width - text.length) / 2);
  return `${" ".repeat(pad)}${text}`;
}

function messageLines(message: ChatMessage, width: number): string {
  const lines = wrap(message.text, Math.max(8, width - 2));
  if (message.role === "user") {
    return lines.map((line, i) => (i === 0 ? `${USER_MARK} ${line}` : `  ${line}`)).join("\n");
  }
  return lines.map((line) => `  ${line}`).join("\n");
}

export function App() {
  const renderer = useRenderer();
  const { width } = useTerminalDimensions();
  const [screen, setScreen] = useState<ChatScreen | null>(null);
  const [draft, setDraft] = useState("");
  const [focused, setFocused] = useState(true);
  const [caretOn, setCaretOn] = useState(true);
  const [reveal, setReveal] = useState(0);
  const gen = useRef(0);
  const screenRef = useRef(screen);
  const draftRef = useRef(draft);
  const focusedRef = useRef(focused);
  const busyRef = useRef(false);
  screenRef.current = screen;
  draftRef.current = draft;
  focusedRef.current = focused;

  const load = async (id?: string) => {
    const ticket = ++gen.current;
    const [sessions, current, messages] = await Promise.all([
      readRoute(API, ROUTES.sessions),
      readRoute(API, id ? sessionRoute(id) : ROUTES.current),
      readRoute(API, id ? messageRoute(id) : ROUTES.messages),
    ]);
    if (ticket !== gen.current) return null;
    const next = assembleScreen(sessions, current, messages);
    setScreen(next);
    return next;
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    let timer = 0;
    const start = setTimeout(() => {
      timer = setInterval(() => setCaretOn((on) => !on), 530);
    }, 530);
    return () => {
      clearTimeout(start);
      clearInterval(timer);
    };
  }, []);

  const welcome = screen?.welcome === true;
  useEffect(() => {
    if (!welcome) {
      setReveal(0);
      return;
    }
    setReveal(0);
    const timer = setInterval(() => {
      setReveal((n) => (n >= WELCOME.length ? n : n + 1));
    }, 16);
    const stop = setTimeout(() => clearInterval(timer), WELCOME.length * 16 + 40);
    return () => {
      clearInterval(timer);
      clearTimeout(stop);
    };
  }, [welcome]);

  const applyClosed = (kind: "empty" | "error", note: string) => {
    setScreen((prev) => {
      if (!prev || prev.messages.length === 0) return blank(note, kind === "error" ? "error" : "empty");
      return { ...prev, note, welcome: false };
    });
  };

  const submit = async () => {
    const text = draftRef.current.trim();
    if (!text || busyRef.current) return;
    busyRef.current = true;
    try {
      let id = screenRef.current?.currentId ?? null;
      if (!id) {
        const created = await postRoute(API, "/chat/sessions", {});
        if (created.kind !== "data") {
          applyClosed(created.kind, created.note);
          return;
        }
        id = sessionId(created.data);
        if (!id) {
          applyClosed("empty", DASH);
          return;
        }
      }
      const sent = await postRoute(API, messageRoute(id), { text });
      if (sent.kind !== "data") {
        applyClosed(sent.kind, sent.note);
        return;
      }
      setDraft("");
      const next = await load(id);
      const reply = replyText(sent.data);
      if (!next || !reply || next.messages.some((message) => message.text === reply)) return;
      if (next.status === "empty" && next.note) return;
      setScreen({
        ...next,
        status: "ok",
        welcome: false,
        messages: [...next.messages, { id: `reply-${id}`, role: "assistant", text: reply }],
      });
    } finally {
      busyRef.current = false;
    }
  };

  const createSession = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    try {
      const created = await postRoute(API, "/chat/sessions", {});
      if (created.kind !== "data") {
        setScreen((prev) => (prev ? { ...prev, note: created.note } : blank(created.note, created.kind)));
        return;
      }
      const id = sessionId(created.data);
      if (!id) return;
      await load(id);
    } finally {
      busyRef.current = false;
    }
  };

  const move = (delta: number) => {
    const sessions = screenRef.current?.sessions ?? [];
    if (sessions.length === 0) return;
    const current = sessions.findIndex((session) => session.id === screenRef.current?.currentId);
    const from = current < 0 ? 0 : current;
    const next = Math.max(0, Math.min(sessions.length - 1, from + delta));
    if (sessions[next].id === screenRef.current?.currentId) return;
    void load(sessions[next].id);
  };

  const onKey = useRef<(key: Key) => void>(() => {});
  onKey.current = (key) => {
    const name = key.name ?? "";
    if (key.ctrl) return;
    if (focusedRef.current) {
      if (name === "escape" || name === "up") {
        setFocused(false);
        return;
      }
      if (name === "return" || name === "enter") {
        void submit();
        return;
      }
      if (name === "backspace") {
        setDraft((value) => value.slice(0, -1));
        return;
      }
      const ch = key.sequence ?? "";
      if (ch.length === 1 && ch >= " ") setDraft((value) => value + ch);
      return;
    }
    if (name === "q") {
      renderer.destroy();
      return;
    }
    if (name === "i" || name === "return" || name === "enter") {
      setFocused(true);
      return;
    }
    if (name === "n") {
      void createSession();
      return;
    }
    if (name === "down" || name === "j") move(1);
    if (name === "up" || name === "k") move(-1);
  };
  useKeyboard((key) => onKey.current(key));

  const threadWidth = Math.max(24, width - 24);
  const sessions = screen?.sessions ?? [];
  const caret = focused ? (caretOn ? "█" : " ") : "";
  const noteColor = screen?.status === "error" ? SOFT : MUTE;

  return (
    <box width="100%" height="100%" flexDirection="row" backgroundColor={BG}>
      <box width={24} flexDirection="column" backgroundColor={BG} border={["right"]} borderColor={HAIR}>
        <box height={1} paddingLeft={1} backgroundColor={BG}>
          <text fg={MUTE}>digichat</text>
        </box>
        <box height={1} backgroundColor={BG}>
          <text fg={HAIR}>{"─".repeat(23)}</text>
        </box>
        <box height={1} paddingLeft={1} backgroundColor={BG}>
          <text fg={MUTE}>{NEW_CHAT}</text>
        </box>
        {sessions.map((session) => {
          const active = session.id === screen?.currentId;
          return (
            <box key={session.id} height={1} paddingLeft={1} backgroundColor={active ? FILL : BG}>
              <text fg={active ? INK : SOFT}>{clip(session.title, 20)}</text>
            </box>
          );
        })}
      </box>
      <box flexGrow={1} flexDirection="column" backgroundColor={BG} paddingLeft={2} paddingRight={2} paddingTop={1}>
        <box flexGrow={1} flexDirection="column" backgroundColor={BG} overflow="hidden">
          {screen?.messages.map((message) => (
            <text key={message.id} fg={message.role === "user" ? INK : SOFT}>
              {messageLines(message, threadWidth - 4)}
            </text>
          ))}
          <box flexGrow={1} backgroundColor={BG} />
          {welcome ? (
            <text fg={INK}>
              {WELCOME.slice(0, reveal)}
              {reveal < WELCOME.length ? "█" : ""}
            </text>
          ) : null}
          {screen?.note ? <text fg={noteColor}>{screen.note}</text> : null}
        </box>
        <box border borderColor={HAIR} backgroundColor={BG} flexDirection="column" paddingLeft={1} paddingRight={1}>
          <box height={1} flexDirection="row" backgroundColor={BG}>
            {draft ? <text fg={INK}>{draft}</text> : null}
            {caret ? <text fg={INK}>{caret}</text> : null}
            {draft ? null : <text fg={MUTE}>{PLACEHOLDER}</text>}
          </box>
          <box height={1} flexDirection="row" backgroundColor={BG}>
            <text fg={MUTE}>{ATTACH}</text>
            <box flexGrow={1} backgroundColor={BG} />
            <text fg={draft.trim() ? SOFT : MUTE}>{SEND}</text>
          </box>
        </box>
        <box height={1} backgroundColor={BG}>
          <text fg={MUTE}>{center(CREDIT, Math.max(10, threadWidth - 4))}</text>
        </box>
      </box>
    </box>
  );
}
