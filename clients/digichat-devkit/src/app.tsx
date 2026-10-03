import { useKeyboard, useRenderer, useTerminalDimensions } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import { DigichatWordmark, WORDMARK_ROWS } from "../../digichat-tui/src/wordmark";
import { GLYPH } from "./glyphs";
import {
  activateStrip,
  backspace,
  blankDraft,
  chatBody,
  liveFrom,
  mainChrome,
  postBaseline,
  rowsFor,
  selectEntry,
  stripRows,
  toggleFlag,
  toggleMcp,
  toggleTool,
  typeInto,
  type ChatTurn,
  type Draft,
  type LiveView,
  type SettingRow,
  type StripRow,
} from "./live";
import { fieldKey as settingKey } from "./present";
import { loadKit, type KitRead } from "./read";

const BG = "#08090b";
const INK = "#eceef0";
const SOFT = "#9aa0a6";
const MUTE = "#7e858b";
const HAIR = "#2a2e33";

const API = (process.env.DIGICHAT_DEVKIT_URL ?? "http://127.0.0.1:3000").replace(/\/+$/, "");
const GROUPS = ["Deployments", "Basics", "Appearance", "Advanced"] as const;
const reading: KitRead = { status: "down", detail: "reading configs", files: [], envs: [] };

type Focus = "compose" | "side" | "tools";
type Key = { name?: string; shift?: boolean; ctrl?: boolean; sequence?: string };

const dimValue = (value: string) =>
  value === "—" ||
  value === "none" ||
  value === "off" ||
  value === "not set" ||
  value === "nothing to export" ||
  value === "no default model";

function clip(text: string, width: number): string {
  if (text.length <= width) return text;
  if (width <= 1) return "…";
  return `${text.slice(0, width - 1)}…`;
}

function windowStart(length: number, index: number, visible: number): number {
  if (length <= visible) return 0;
  return Math.max(0, Math.min(index, length - visible));
}

function groupAt(rows: SettingRow[], index: number): string {
  for (let i = Math.min(Math.max(index, 0), rows.length - 1); i >= 0; i--) {
    const row = rows[i];
    if (row.kind === "group") return row.text;
  }
  return "Deployments";
}

function welcomeText(title: string | null): string {
  return title ?? "";
}

export function App() {
  const renderer = useRenderer();
  const { width, height } = useTerminalDimensions();
  const [read, setRead] = useState<KitRead>(reading);
  const [draft, setDraft] = useState<Draft>(blankDraft());
  const [focus, setFocus] = useState<Focus>("compose");
  const [side, setSide] = useState(0);
  const [tool, setTool] = useState(0);
  const [compose, setCompose] = useState("");
  const [turns, setTurns] = useState<ChatTurn[]>([]);
  const [note, setNote] = useState("");
  const [shown, setShown] = useState(0);
  const [blink, setBlink] = useState(true);
  const [reveal, setReveal] = useState(0);

  const focusRef = useRef(focus);
  const draftRef = useRef(draft);
  const composeRef = useRef(compose);
  const turnsRef = useRef(turns);
  const sideRef = useRef(side);
  const toolRef = useRef(tool);
  const busyRef = useRef(false);
  focusRef.current = focus;
  draftRef.current = draft;
  composeRef.current = compose;
  turnsRef.current = turns;
  sideRef.current = side;
  toolRef.current = tool;

  const view = liveFrom(read, draft);
  const rows = rowsFor(read, draft);
  const strip = stripRows(view);
  const viewRef = useRef(view);
  const rowsRef = useRef(rows);
  const stripRef = useRef(strip);
  viewRef.current = view;
  rowsRef.current = rows;
  stripRef.current = strip;

  useEffect(() => {
    const ac = new AbortController();
    const timer = setTimeout(() => ac.abort(), 1500);
    let cancel = false;
    void loadKit(API, ac.signal).then((next) => {
      if (!cancel) setRead(next);
    });
    return () => {
      cancel = true;
      clearTimeout(timer);
      ac.abort();
    };
  }, []);

  useEffect(() => {
    setShown(0);
  }, [read.detail]);

  useEffect(() => {
    if (shown >= read.detail.length) return;
    const timer = setTimeout(() => setShown((n) => Math.min(read.detail.length, n + 1)), 16);
    return () => clearTimeout(timer);
  }, [shown, read.detail]);

  useEffect(() => {
    const timer = setInterval(() => setBlink((on) => !on), 530);
    return () => clearInterval(timer);
  }, []);

  const greeting = turns.length === 0 ? welcomeText(view.welcomeTitle) : "";
  useEffect(() => {
    setReveal(0);
  }, [greeting]);

  useEffect(() => {
    if (!greeting || reveal >= greeting.length) return;
    const timer = setTimeout(() => setReveal((n) => Math.min(greeting.length, n + 1)), 16);
    return () => clearTimeout(timer);
  }, [greeting, reveal]);

  useEffect(() => {
    setSide((index) => Math.max(0, Math.min(index, Math.max(0, rows.length - 1))));
  }, [rows.length]);

  useEffect(() => {
    setTool((index) => Math.max(0, Math.min(index, Math.max(0, strip.length - 1))));
  }, [strip.length]);

  const send = async () => {
    const text = composeRef.current.trim();
    if (!text || busyRef.current) return;
    busyRef.current = true;
    const id = `u${turnsRef.current.length + 1}`;
    const body = chatBody(viewRef.current, turnsRef.current, text, id);
    setTurns((prev) => [...prev, { id, role: "user", text }]);
    setCompose("");
    setNote("sending");
    try {
      const result = await postBaseline(API, body);
      const reply: ChatTurn =
        result.kind === "error"
          ? { id: `e${id}`, role: "system", text: result.detail }
          : { id: `a${id}`, role: "assistant", text: result.text };
      setTurns((prev) => [...prev, reply]);
      setNote("");
    } finally {
      busyRef.current = false;
    }
  };

  const onKey = useRef<(key: Key) => void>(() => {});
  onKey.current = (key) => {
    const name = key.name ?? "";
    if (key.ctrl) return;
    const typed = name === "space" ? " " : (key.sequence ?? "");
    const printable = typed.length === 1 && typed >= " ";
    if (name === "tab") {
      const order: Focus[] = ["compose", "side", "tools"];
      const index = order.indexOf(focusRef.current);
      const step = key.shift ? -1 : 1;
      setFocus(order[(index + step + order.length) % order.length]);
      setNote("");
      return;
    }
    if (name === "escape") {
      setFocus(focusRef.current === "compose" ? "side" : "compose");
      setNote("");
      return;
    }
    if (focusRef.current === "compose") {
      if (name === "q" && composeRef.current === "") {
        renderer.destroy();
        return;
      }
      if (name === "return" || name === "enter") {
        void send();
        return;
      }
      if (name === "backspace") {
        setCompose((value) => value.slice(0, -1));
        return;
      }
      if ((name === "up" || name === "down") && composeRef.current === "") {
        const list = viewRef.current.suggestions;
        if (list.length === 0) return;
        const current = list.indexOf(composeRef.current);
        const from = current < 0 ? (name === "down" ? -1 : 0) : current;
        const next = name === "down" ? Math.min(list.length - 1, from + 1) : Math.max(0, from - 1);
        setCompose(list[next] ?? "");
        return;
      }
      if (printable) setCompose((value) => value + ch);
      return;
    }
    if (focusRef.current === "tools") {
      if (name === "up" || name === "k") {
        setTool((index) => Math.max(0, index - 1));
        return;
      }
      if (name === "down" || name === "j") {
        setTool((index) => Math.min(stripRef.current.length - 1, index + 1));
        return;
      }
      if (name === "space" || name === "return" || name === "enter") {
        const row = stripRef.current[toolRef.current];
        if (!row || row.kind === "empty") {
          setNote("none");
          return;
        }
        setDraft((current) => activateStrip(current, row, viewRef.current));
        setNote("");
        return;
      }
      if (name === "q") renderer.destroy();
      return;
    }
    const row = rowsRef.current[sideRef.current];
    const textField = row?.kind === "field" && !row.toggle;
    if (name === "up" || (name === "k" && !textField)) {
      setSide((index) => Math.max(0, index - 1));
      setNote("");
      return;
    }
    if (name === "down" || (name === "j" && !textField)) {
      setSide((index) => Math.min(rowsRef.current.length - 1, index + 1));
      setNote("");
      return;
    }
    if (row?.kind === "mark" && row.toggle === "entry" && row.id && (name === "return" || name === "enter")) {
      setDraft(selectEntry(row.id));
      setTurns([]);
      setCompose("");
      setNote("");
      return;
    }
    if (row?.kind === "field" && (name === "space" || name === "return" || name === "enter")) {
      if (row.toggle === "flag") {
        setDraft((current) => toggleFlag(current, settingKey(row.pane, row.label), row.value));
        setNote("");
        return;
      }
      if (row.toggle === "tool" && row.id) {
        const on = row.value === "on" || row.value === "default on";
        setDraft((current) => toggleTool(current, row.id as string, on));
        setNote("");
        return;
      }
      if (row.toggle === "mcp" && row.id) {
        const on = !row.value.endsWith(" · off") && row.value !== "—";
        setDraft((current) => toggleMcp(current, row.id as string, on));
        setNote("");
        return;
      }
    }
    if (row?.kind === "field" && row.secret && (printable || name === "backspace")) {
      setNote("redacted");
      return;
    }
    if (row?.kind === "field" && !row.toggle && !row.secret) {
      const setting = settingKey(row.pane, row.label);
      if (name === "backspace") {
        setDraft((current) => backspace(current, setting, row.value, false));
        return;
      }
      if (printable) {
        setDraft((current) => typeInto(current, setting, row.value, false, typed));
        return;
      }
    }
    if (name === "q") renderer.destroy();
  };
  useKeyboard((key) => onKey.current(key));

  const sideWidth = Math.max(40, Math.min(54, Math.floor((width || 120) * 0.36)));
  const visible = Math.max(8, (height || 32) - 6 - WORDMARK_ROWS);
  const start = windowStart(rows.length, side, visible);
  const shownRows = rows.slice(start, start + visible);
  const stripStart = windowStart(strip.length, tool, 4);
  const shownStrip = strip.slice(stripStart, stripStart + 4);
  const group = groupAt(rows, side);
  const valueWidth = Math.max(8, sideWidth - 28);
  const headerReveal = read.detail.slice(0, shown);
  const accent = view.accent ?? INK;

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <DigichatWordmark cols={width} />
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        <text fg={INK}>devkit</text>
        <text fg={MUTE}>{`  ${API}  `}</text>
        <text fg={SOFT}>{headerReveal}</text>
        {shown < read.detail.length && blink ? <text fg={INK}>█</text> : null}
      </box>
      <box flexGrow={1} flexDirection="row" backgroundColor={BG}>
        <box width={sideWidth} flexDirection="column" border borderColor={focus === "side" ? INK : HAIR} backgroundColor={BG}>
          <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
            {GROUPS.map((item) => {
              const on = item === group;
              return (
                <text key={item} fg={on ? INK : MUTE}>
                  {on ? `${GLYPH.user} ${item} ` : `${GLYPH.system} ${item} `}
                </text>
              );
            })}
          </box>
          <box flexGrow={1} paddingLeft={1} paddingRight={1} flexDirection="column" backgroundColor={BG} overflow="hidden">
            {shownRows.map((row, index) => (
              <box key={`${start + index}`} height={1} flexDirection="row" backgroundColor={BG}>
                <SettingLine
                  row={row}
                  hot={focus === "side" && start + index === side}
                  caret={blink && focus === "side" && start + index === side && row.kind === "field"}
                  valueWidth={valueWidth}
                />
              </box>
            ))}
          </box>
          <box height={1} paddingLeft={1} backgroundColor={BG}>
            <text fg={MUTE}>{`${start + 1}–${start + shownRows.length}/${rows.length}`}</text>
          </box>
        </box>
        <box flexGrow={1} flexDirection="column" backgroundColor={BG} paddingLeft={1} paddingRight={1}>
          <ChromeRows view={view} detail={read.detail} turns={turns} reveal={reveal} blink={blink} accent={accent} />
          {view.gate ? (
            <box height={1} backgroundColor={BG}>
              <text fg={MUTE}>{`· gate ${view.gate}`}</text>
            </box>
          ) : null}
          {view.chips.length > 0 ? (
            <box height={1} backgroundColor={BG}>
              <text fg={MUTE}>{`· ${view.chips.join("  ")}`}</text>
            </box>
          ) : null}
          {view.issues.map((issue) => (
            <box key={issue} height={1} backgroundColor={BG}>
              <text fg={MUTE}>{`· ${issue}`}</text>
            </box>
          ))}
          <box flexGrow={1} border borderColor={HAIR} flexDirection="column" backgroundColor={BG} paddingLeft={1} paddingRight={1} overflow="hidden">
            {turns.map((turn) => (
              <TurnLine key={turn.id} turn={turn} accent={accent} alignRight={view.alignRight} />
            ))}
            {turns.length === 0 && !view.configured ? (
              <text fg={MUTE}>{`${GLYPH.system} ${read.detail}`}</text>
            ) : null}
          </box>
          {shownStrip.map((row, index) => (
            <box key={`${stripStart + index}`} height={1} flexDirection="row" backgroundColor={BG}>
              <StripLine
                row={row}
                hot={focus === "tools" && stripStart + index === tool}
                caret={blink && focus === "tools" && stripStart + index === tool}
              />
            </box>
          ))}
          <box height={1} flexDirection="row" backgroundColor={BG}>
            {view.attachments ? <text fg={MUTE}>+ </text> : null}
            <text fg={INK}>{`${GLYPH.user} `}</text>
            {compose ? <text fg={INK}>{compose}</text> : null}
            {focus === "compose" && blink ? <text fg={INK}>█</text> : null}
            {!compose && view.placeholder ? <text fg={MUTE}>{view.placeholder}</text> : null}
          </box>
        </box>
      </box>
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        <text fg={MUTE}>tab focus   ↑↓ move   space toggle   enter send   q quit</text>
        {note ? <text fg={SOFT}>{`   ${note}`}</text> : null}
      </box>
    </box>
  );
}

function ChromeRows({
  view,
  detail,
  turns,
  reveal,
  blink,
  accent,
}: {
  view: LiveView;
  detail: string;
  turns: ChatTurn[];
  reveal: number;
  blink: boolean;
  accent: string;
}) {
  const chrome = mainChrome(view, detail, turns);
  const title = chrome.find((row) => row.slot === "title")?.text ?? "—";
  const headline = chrome.find((row) => row.slot === "headline")?.text ?? "—";
  const welcome = chrome.filter((row) => row.slot === "welcome");
  const welcomeTitle = welcome[0]?.text ?? "—";
  const welcomeShown = welcomeTitle === "—" ? welcomeTitle : welcomeTitle.slice(0, reveal);
  const welcomeBody = welcome[1]?.text ?? "—";
  const titleDone = welcomeTitle === "—" || reveal >= welcomeTitle.length;
  return (
    <box flexDirection="column" backgroundColor={BG}>
      <box height={1} flexDirection="row" backgroundColor={BG}>
        <text fg={MUTE}>title  </text>
        <text fg={title === "—" ? MUTE : accent}>{title}</text>
      </box>
      <box height={1} backgroundColor={BG}>
        <text fg={headline === "—" ? MUTE : INK}>{headline}</text>
      </box>
      <box height={1} flexDirection="row" backgroundColor={BG}>
        <text fg={MUTE}>welcome  </text>
        <text fg={view.welcomeTitle ? INK : MUTE}>{welcomeShown}</text>
        {view.welcomeTitle && reveal < view.welcomeTitle.length && blink ? <text fg={INK}>█</text> : null}
      </box>
      <box height={1} backgroundColor={BG}>
        <text fg={view.welcomeBody && titleDone ? SOFT : MUTE}>{titleDone ? welcomeBody : "—"}</text>
      </box>
      {view.suggestions.map((item) => (
        <box key={item} height={1} backgroundColor={BG}>
          <text fg={MUTE}>{`${GLYPH.system} ${item}`}</text>
        </box>
      ))}
    </box>
  );
}

function SettingLine({
  row,
  hot,
  caret,
  valueWidth,
}: {
  row: SettingRow;
  hot: boolean;
  caret: boolean;
  valueWidth: number;
}) {
  if (row.kind === "group") return <text fg={INK}>{`${GLYPH.assistant} ${row.text}`}</text>;
  if (row.kind === "head") return <text fg={MUTE}>{`${GLYPH.system} ${row.text}`}</text>;
  if (row.kind === "mark") {
    return <text fg={row.on ? INK : MUTE}>{`${row.on ? GLYPH.assistant : GLYPH.system} ${row.text}`}</text>;
  }
  const mark = hot ? GLYPH.user : " ";
  return (
    <box flexDirection="row" backgroundColor={BG}>
      <text fg={hot ? INK : MUTE}>{`${mark} ${clip(row.label, 24)}`}</text>
      <text fg={dimValue(row.value) ? MUTE : SOFT}>{`  ${clip(row.value, valueWidth)}`}</text>
      {caret ? <text fg={INK}>█</text> : null}
    </box>
  );
}

function StripLine({ row, hot, caret }: { row: StripRow; hot: boolean; caret: boolean }) {
  const label =
    row.kind === "model"
      ? `model  ${row.value}`
      : row.kind === "tool"
        ? `tool  ${row.label}  ${row.on ? "on" : "off"}`
        : row.kind === "mcp"
          ? `mcp  ${row.label}  ${row.on ? "on" : "off"}`
          : `${row.slot}  ${row.text}`;
  return (
    <box flexDirection="row" backgroundColor={BG}>
      <text fg={hot ? INK : MUTE}>{`${hot ? GLYPH.user : GLYPH.system} ${label}`}</text>
      {caret ? <text fg={INK}>█</text> : null}
    </box>
  );
}

function TurnLine({ turn, accent, alignRight }: { turn: ChatTurn; accent: string; alignRight: boolean }) {
  const glyph = turn.role === "user" ? GLYPH.user : turn.role === "assistant" ? GLYPH.assistant : GLYPH.system;
  const color = turn.role === "user" ? INK : turn.role === "assistant" ? accent : MUTE;
  return (
    <box flexDirection="row" backgroundColor={BG}>
      {alignRight && turn.role === "user" ? <box flexGrow={1} backgroundColor={BG} /> : null}
      <text fg={color}>{`${glyph} ${turn.text}`}</text>
    </box>
  );
}
