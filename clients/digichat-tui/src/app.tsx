import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import {
  attachmentLine,
  exportMarkdown,
  historySkeleton,
  loadingStatus,
  renderMessages,
  sessionTitle,
  spinnerFrame,
  suggestionLines,
  welcomeLines,
  clip,
  type ThreadLine,
  type Tone,
} from "./chrome";
import { INITIAL_UI, reduceKey, type KeyEffect, type UiState } from "./keys";
import { choiceOptions, mentionRows, paletteRows, paneRows, type PaneCatalog } from "./palette";
import {
  DASH,
  PLACEHOLDER,
  ROUTES,
  CREDIT,
  WELCOME,
  assembleFromBff,
  basename,
  chatBaseUrl,
  conversationRoute,
  fetchByokModels,
  fetchMcpServers,
  filePartsFromPaths,
  postChat,
  postRoute,
  putRoute,
  readRoute,
  sessionId,
  toUiMessages,
  type ChatMessage,
  type ChatScreen,
  type UiChatMessage,
} from "./read";
import { ATTACH, BG, DANGER, FILL, HAIR, INK, MUTE, NEW_CHAT, SCROLL, SEND, SOFT, STOP, VOICE } from "./theme";
import { DigichatWordmark, WORDMARK_ROWS } from "./wordmark";

const API = chatBaseUrl();

const TONE: Record<Tone, string> = { ink: INK, soft: SOFT, mute: MUTE, danger: DANGER };

const blank = (note: string, status: ChatScreen["status"]): ChatScreen => ({
  status,
  sessions: [],
  currentId: null,
  messages: [],
  note,
  welcome: false,
  canSend: true,
});

function center(text: string, width: number): string {
  if (text.length >= width) return text;
  const pad = Math.floor((width - text.length) / 2);
  return `${" ".repeat(pad)}${text}`;
}

function lastText(messages: readonly ChatMessage[], role: ChatMessage["role"]): string {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message || message.role !== role || message.tool) continue;
    if (message.text.trim() && message.text !== DASH) return message.text;
  }
  return "";
}

function lastFoldable(messages: readonly ChatMessage[]): string | null {
  for (let index = messages.length - 1; index >= 0; index -= 1) {
    const message = messages[index];
    if (!message) continue;
    if (message.tool) return message.id;
    if (message.reasoning) return `${message.id}:reasoning`;
  }
  return null;
}

function toolNames(messages: readonly ChatMessage[]): string[] {
  const names: string[] = [];
  for (const message of messages) {
    if (message.tool?.name && !names.includes(message.tool.name)) names.push(message.tool.name);
  }
  return names;
}

function writeClipboard(text: string) {
  const payload = Buffer.from(text, "utf8").toString("base64");
  try {
    process.stdout.write(`\u001b]52;c;${payload}\u0007`);
  } catch {
    return;
  }
}

function windowStart(index: number, length: number, size: number): number {
  if (length <= size) return 0;
  const start = Math.min(index, Math.max(0, length - size));
  return Math.max(0, Math.min(start, index));
}

export function App() {
  const renderer = useRenderer();
  const { width, height } = useTerminalDimensions();
  const [screen, setScreen] = useState<ChatScreen | null>(null);
  const [ui, setUi] = useState<UiState>(INITIAL_UI);
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  const [caretOn, setCaretOn] = useState(true);
  const [reveal, setReveal] = useState(0);
  const [catalog, setCatalog] = useState<PaneCatalog>({});
  const gen = useRef(0);
  const screenRef = useRef(screen);
  const uiRef = useRef(ui);
  const busyRef = useRef(busy);
  const catalogRef = useRef(catalog);
  const abortRef = useRef<AbortController | null>(null);
  screenRef.current = screen;
  uiRef.current = ui;
  busyRef.current = busy;
  catalogRef.current = catalog;

  const load = async (id?: string) => {
    const ticket = ++gen.current;
    const list = await readRoute(API, ROUTES.conversations);
    if (ticket !== gen.current) return null;
    const preferred =
      id ??
      (list.kind === "data"
        ? (list.data as { conversations?: Array<{ id?: string }> })?.conversations?.[0]?.id
        : null) ??
      null;
    const preferredId = typeof preferred === "string" && preferred.length > 0 ? preferred : null;
    const current = preferredId ? await readRoute(API, conversationRoute(preferredId)) : null;
    if (ticket !== gen.current) return null;
    const next = assembleFromBff(list, current, preferredId);
    setScreen(next);
    return next;
  };

  useEffect(() => {
    void load();
  }, []);

  useEffect(() => {
    const timer = setInterval(() => setTick((value) => value + 1), 80);
    return () => clearInterval(timer);
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

  const welcome = screen?.welcome === true && !ui.pane;
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
    if (!note) return;
    setScreen((prev) => {
      if (!prev || prev.messages.length === 0) return blank(note, kind === "error" ? "error" : "empty");
      return { ...prev, note, welcome: false };
    });
  };

  const submitText = async (text: string, attachmentPaths: string[] = []) => {
    const body = text.trim();
    if ((!body && attachmentPaths.length === 0) || busyRef.current) return;
    const controller = new AbortController();
    abortRef.current = controller;
    busyRef.current = true;
    setBusy(true);
    try {
      let id = screenRef.current?.currentId ?? null;
      if (!id) {
        const created = await postRoute(API, ROUTES.conversations, {}, controller.signal);
        if (controller.signal.aborted) return;
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
      const prior = screenRef.current?.messages ?? [];
      const userId = `u-${Date.now()}`;
      const { parts: fileParts, skipped } = await filePartsFromPaths(attachmentPaths);
      if (controller.signal.aborted) return;
      if (skipped.length > 0) {
        setUi((prev) => ({
          ...prev,
          note: `skipped attach: ${skipped.join(", ")}`,
        }));
      }
      const userParts = [
        ...(body ? [{ type: "text" as const, text: body }] : []),
        ...fileParts,
      ];
      if (userParts.length === 0) {
        applyClosed("empty", "nothing to send");
        return;
      }
      const userMsg: UiChatMessage = { id: userId, role: "user", parts: userParts };
      const uiMessages = [...toUiMessages(prior), userMsg];
      const sent = await postChat(API, id, uiMessages, controller.signal, uiRef.current.prefs);
      if (controller.signal.aborted) return;
      if (sent.kind !== "text") {
        applyClosed("error", sent.detail);
        return;
      }
      const assistantId = `a-${Date.now()}`;
      const displayText =
        body || (fileParts.length > 0 ? fileParts.map((p) => p.filename).join(", ") : DASH);
      const nextMessages: ChatMessage[] = [
        ...prior,
        { id: userId, role: "user", text: displayText, tool: null, reasoning: "", at: "" },
        { id: assistantId, role: "assistant", text: sent.text, tool: null, reasoning: "", at: "" },
      ];
      void putRoute(API, conversationRoute(id), {
        messages: toUiMessages(nextMessages),
      }, controller.signal);
      setScreen({
        status: "ok",
        sessions: screenRef.current?.sessions ?? [{ id, title: DASH }],
        currentId: id,
        messages: nextMessages,
        note: "",
        welcome: false,
        canSend: true,
      });
    } finally {
      if (abortRef.current === controller) abortRef.current = null;
      busyRef.current = false;
      setBusy(false);
    }
  };

  const loadCatalog = async (pane: "models" | "mcp" | "tools") => {
    if (pane === "tools") {
      setCatalog((prev) => ({ ...prev, tools: toolNames(screenRef.current?.messages ?? []) }));
      return;
    }
    if (pane === "models") {
      const provider = uiRef.current.prefs.provider || "openrouter";
      const result = await fetchByokModels(API, provider);
      if (result.kind === "ok") {
        setCatalog((prev) => ({
          ...prev,
          models: result.models,
          modelsNote: result.models.length === 0 ? "No models returned." : "",
        }));
      } else {
        setCatalog((prev) => ({ ...prev, models: [], modelsNote: result.detail }));
      }
      return;
    }
    const result = await fetchMcpServers(API);
    if (result.kind === "ok") {
      setCatalog((prev) => ({
        ...prev,
        mcp: result.servers,
        mcpNote: result.servers.length === 0 ? "No MCP servers." : "",
      }));
    } else {
      setCatalog((prev) => ({ ...prev, mcp: [], mcpNote: result.detail }));
    }
  };

  const createSession = async () => {
    if (busyRef.current) return;
    busyRef.current = true;
    setBusy(true);
    try {
      const created = await postRoute(API, ROUTES.conversations, {});
      if (created.kind !== "data") {
        const kind = created.kind === "error" ? "error" : "empty";
        setScreen((prev) => (prev ? { ...prev, note: created.note } : blank(created.note, kind)));
        return;
      }
      const id = sessionId(created.data);
      if (!id) return;
      await load(id);
    } finally {
      busyRef.current = false;
      setBusy(false);
    }
  };

  const move = (delta: number) => {
    const sessions = screenRef.current?.sessions ?? [];
    if (sessions.length === 0) return;
    const current = sessions.findIndex((session) => session.id === screenRef.current?.currentId);
    const from = current < 0 ? 0 : current;
    const next = Math.max(0, Math.min(sessions.length - 1, from + delta));
    if (sessions[next]?.id === screenRef.current?.currentId) return;
    const id = sessions[next]?.id;
    if (id) void load(id);
  };

  const runEffect = (effect: KeyEffect | null) => {
    if (!effect) return;
    if (effect.type === "quit") {
      renderer.destroy();
      return;
    }
    if (effect.type === "abort") {
      abortRef.current?.abort();
      return;
    }
    if (effect.type === "new-session") {
      void createSession();
      return;
    }
    if (effect.type === "move-session") {
      move(effect.delta);
      return;
    }
    if (effect.type === "submit") {
      void submitText(effect.text, effect.attachments);
      return;
    }
    if (effect.type === "copy") {
      const text = lastText(screenRef.current?.messages ?? [], "assistant");
      if (text) writeClipboard(text);
      return;
    }
    if (effect.type === "load-catalog") {
      if (effect.pane === "models" || effect.pane === "mcp" || effect.pane === "tools") {
        void loadCatalog(effect.pane);
      }
      return;
    }
    if (effect.type === "redo") {
      const text = lastText(screenRef.current?.messages ?? [], "user");
      if (text) void submitText(text);
      else void load();
    }
  };

  const onKey = useRef<(key: { name?: string; ctrl?: boolean; sequence?: string }) => void>(() => {});
  onKey.current = (key) => {
    const messages = screenRef.current?.messages ?? [];
    const result = reduceKey(uiRef.current, key, {
      busy: busyRef.current,
      canSend: screenRef.current?.canSend !== false,
      sessionCount: screenRef.current?.sessions.length ?? 0,
      canCopy: Boolean(lastText(messages, "assistant")),
      canRetry: screenRef.current?.status === "error",
      lastUserText: lastText(messages, "user"),
      lastFoldable: lastFoldable(messages),
      toolNames: toolNames(messages),
      catalog: catalogRef.current,
    });
    uiRef.current = result.state;
    setUi(result.state);
    runEffect(result.effect);
  };
  useKeyboard((key) => onKey.current(key));

  const rail = Math.min(28, Math.max(18, Math.floor(width * 0.28)));
  const threadWidth = Math.max(24, width - rail - 4);
  const spinner = spinnerFrame(tick);
  const messages = screen?.messages ?? [];
  const slash = paletteRows(ui.draft, ui.prefs);
  const mentions = mentionRows(ui.draft, toolNames(messages));
  const composing = ui.focus === "composer" && !ui.choice && !ui.pathing;
  const showPalette = composing && ui.draft.startsWith("/") && !ui.draft.endsWith(" ");
  const showMentions = composing && !showPalette && /(?:^|\s)@[^\s]*$/.test(ui.draft);
  const choiceList = ui.choice ? choiceOptions(ui.choice.id, ui.prefs) : [];
  const rows = ui.choice
    ? choiceList.map((row) => ({ id: row.value, label: row.label, description: "" }))
    : showPalette
      ? slash
      : showMentions
        ? mentions
        : [];
  const listIndex = ui.choice ? ui.choice.index : ui.paletteIndex;
  const listSize = Math.min(8, Math.max(rows.length, showPalette && rows.length === 0 ? 1 : rows.length));
  const listStart = windowStart(listIndex, rows.length, listSize);
  const visibleRows = rows.slice(listStart, listStart + listSize);

  const body: ThreadLine[] = [];
  if (!screen) {
    body.push({ text: loadingStatus(spinner), tone: "mute" });
    body.push(...historySkeleton(threadWidth));
  } else if (!ui.pane) {
    body.push(
      ...renderMessages({
        messages,
        width: threadWidth,
        open: ui.open,
        busy,
        spinner,
        actions: true,
      }),
    );
    body.push(...suggestionLines([], threadWidth));
    if (screen.welcome) body.push(...welcomeLines(WELCOME.slice(0, reveal), reveal >= WELCOME.length));
    if (screen.note) {
      body.push({ text: screen.status === "error" ? `! ${screen.note}` : screen.note, tone: screen.status === "error" ? "danger" : "mute" });
      if (screen.status === "error") body.push({ text: "retry", tone: "mute" });
    }
  }

  const pane = ui.pane;
  const paneBody: ThreadLine[] =
    pane === "export"
      ? exportMarkdown(messages).split("\n").map((text) => ({ text: text || " ", tone: "soft" as const }))
      : pane
        ? paneRows(pane, ui.prefs, catalog).map((row, index) => ({
            text: `${index === ui.paneIndex ? ">" : " "} ${row.label}${row.description ? `  ${row.description}` : ""}`,
            tone: index === ui.paneIndex ? "ink" : "soft",
          }))
        : [];
  if (pane === "export" && paneBody.length === 0) paneBody.push({ text: "nothing to export", tone: "mute" });

  const maxLines = Math.max(
    4,
    height - 8 - WORDMARK_ROWS - (rows.length > 0 || (showPalette && slash.length === 0) ? listSize + 2 : 0) - ui.attachments.length,
  );
  const scroll = Math.max(0, Math.min(ui.scroll, Math.max(0, body.length - 1)));
  const shown = body.slice(Math.max(0, body.length - maxLines - scroll), Math.max(0, body.length - scroll));
  const caret = ui.focus === "composer" && ui.tray === "input" && !ui.pathing ? (caretOn ? "█" : " ") : "";
  const sendGlyph = busy ? STOP : SEND;
  const sendOn = busy || (ui.draft.trim().length > 0 && screen?.canSend !== false);
  const draftText = ui.pathing ? (ui.path || "path") : ui.draft;
  const status = !screen ? "" : ui.note;

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <DigichatWordmark cols={width} />
      <box flexGrow={1} flexDirection="row" backgroundColor={BG}>
      <box width={rail} flexDirection="column" backgroundColor={BG} border={["right"]} borderColor={HAIR}>
        <box height={1} paddingLeft={1} paddingRight={1} flexDirection="row" border={["bottom"]} borderColor={HAIR} backgroundColor={BG}>
          <box flexGrow={1} backgroundColor={BG} />
          <text fg={MUTE}>{NEW_CHAT}</text>
        </box>
        {(screen?.sessions ?? []).map((session) => {
          const active = session.id === screen?.currentId;
          return (
            <box key={session.id} height={1} paddingLeft={1} paddingRight={1} backgroundColor={active ? FILL : BG}>
              <text fg={active ? INK : SOFT}>{clip(sessionTitle(session.title), rail - 4)}</text>
            </box>
          );
        })}
      </box>
      <box flexGrow={1} flexDirection="column" backgroundColor={BG} paddingLeft={2} paddingRight={2} paddingTop={1}>
        <box flexGrow={1} flexDirection="column" backgroundColor={BG} overflow="hidden">
          {pane
            ? paneBody.map((line, index) => (
                <text key={`pane-${index}`} fg={TONE[line.tone]}>
                  {clip(line.text, threadWidth)}
                </text>
              ))
            : shown.map((line, index) => (
                <text key={`line-${index}`} fg={TONE[line.tone]}>
                  {clip(line.text, threadWidth)}
                </text>
              ))}
        </box>
        {scroll > 0 ? (
          <box height={1} backgroundColor={BG}>
            <text fg={MUTE}>{center(`${SCROLL} Scroll to bottom`, threadWidth)}</text>
          </box>
        ) : null}
        {ui.choice || showPalette || showMentions ? (
          <box border={["left", "right", "top"]} borderColor={HAIR} backgroundColor={BG} flexDirection="column">
            {rows.length === 0 ? (
              <box height={1} paddingLeft={1} backgroundColor={BG}>
                <text fg={MUTE}>{showMentions ? "No matching tools" : "No matching commands"}</text>
              </box>
            ) : (
              visibleRows.map((row, index) => {
                const active = listStart + index === listIndex;
                return (
                  <box key={row.id} height={1} paddingLeft={1} paddingRight={1} flexDirection="row" backgroundColor={active ? FILL : BG}>
                    <text fg={INK}>{clip(row.label, 22)}</text>
                    <box flexGrow={1} backgroundColor={active ? FILL : BG} />
                    <text fg={MUTE}>{clip(row.description, Math.max(8, threadWidth - 26))}</text>
                  </box>
                );
              })
            )}
          </box>
        ) : null}
        {ui.attachments.map((path) => (
          <box key={path} height={1} backgroundColor={BG}>
            <text fg={SOFT}>{attachmentLine(basename(path))}</text>
          </box>
        ))}
        <box border borderColor={HAIR} backgroundColor={BG} flexDirection="column" paddingLeft={1} paddingRight={1}>
          <box height={1} flexDirection="row" backgroundColor={BG}>
            {draftText ? <text fg={ui.pathing && !ui.path ? MUTE : INK}>{clip(draftText, threadWidth - 2)}</text> : null}
            {caret ? <text fg={INK}>{caret}</text> : null}
            {draftText ? null : <text fg={MUTE}>{PLACEHOLDER}</text>}
          </box>
          <box height={1} flexDirection="row" backgroundColor={BG}>
            <text fg={ui.tray === "attach" || ui.pathing ? INK : MUTE}>{ATTACH}</text>
            <box flexGrow={1} backgroundColor={BG} />
            <text fg={ui.tray === "voice" ? INK : MUTE}>{VOICE}</text>
            <text fg={MUTE}>  </text>
            <text fg={sendOn || ui.tray === "send" ? SOFT : MUTE}>{sendGlyph}</text>
          </box>
        </box>
        {status ? (
          <box height={1} backgroundColor={BG}>
            <text fg={MUTE}>{clip(status, threadWidth)}</text>
          </box>
        ) : null}
        <box height={1} border={["top"]} borderColor={HAIR} backgroundColor={BG}>
          <text fg={MUTE}>{center(CREDIT, threadWidth)}</text>
        </box>
      </box>
      </box>
    </box>
  );
}
