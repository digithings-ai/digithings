import { useKeyboard, useRenderer } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import { GLYPH } from "./glyphs";
import { panesFor, type Line, type PaneModel } from "./present";
import { loadKit, type KitRead } from "./read";

const BG = "#08090b";
const INK = "#eceef0";
const SOFT = "#9aa0a6";
const MUTE = "#7e858b";
const HAIR = "#2a2e33";

const API = (process.env.DIGICHAT_DEVKIT_URL ?? "http://127.0.0.1:3000").replace(/\/+$/, "");
const VISIBLE = 8;
const GROUPS = ["Basics", "Appearance", "Advanced"] as const;

const reading: KitRead = { status: "down", detail: "reading configs", files: [], envs: [] };

type Key = { name?: string; shift?: boolean };

const dimValue = (value: string) =>
  value === "—" || value === "none" || value === "no session" || value === "nothing to export";

function windowStart(length: number, index: number): number {
  if (length <= VISIBLE) return 0;
  return Math.max(0, Math.min(index, length - VISIBLE));
}

function LineRow({
  line,
  hot,
  caret,
}: {
  line: Line;
  hot: boolean;
  caret: boolean;
}) {
  if (line.kind === "head") {
    return <text fg={MUTE}>{`${GLYPH.system} ${line.text}`}</text>;
  }
  if (line.kind === "mark") {
    const mark = line.on ? GLYPH.assistant : GLYPH.system;
    return <text fg={line.on ? INK : MUTE}>{`${mark} ${line.text}`}</text>;
  }
  const mark = hot ? GLYPH.user : " ";
  return (
    <box flexDirection="row" backgroundColor={BG}>
      <text fg={hot ? INK : MUTE}>{`${mark} ${line.label}`}</text>
      <text fg={dimValue(line.value) ? MUTE : SOFT}>{`  ${line.value}`}</text>
      {caret ? <text fg={INK}>█</text> : null}
    </box>
  );
}

function PaneView({
  pane,
  hot,
  field,
  caret,
}: {
  pane: PaneModel;
  hot: boolean;
  field: number;
  caret: boolean;
}) {
  const start = hot ? windowStart(pane.lines.length, field) : 0;
  const shown = pane.lines.slice(start, start + VISIBLE);
  const more = pane.lines.length > VISIBLE ? `${start + 1}–${start + shown.length}/${pane.lines.length}` : pane.footer;
  return (
    <box flexGrow={1} flexBasis={0} border borderColor={hot ? INK : HAIR} flexDirection="column" backgroundColor={BG} overflow="hidden">
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        <text fg={hot ? INK : MUTE}>{hot ? `${GLYPH.assistant} ` : `${GLYPH.system} `}</text>
        <text fg={INK}>{pane.title}</text>
      </box>
      <box flexGrow={1} paddingLeft={1} paddingRight={1} flexDirection="column" backgroundColor={BG}>
        {shown.map((line, i) => (
          <box key={`${pane.id}-${start + i}`} height={1} backgroundColor={BG}>
            <LineRow line={line} hot={hot && line.kind === "field" && start + i === field} caret={caret && hot && start + i === field} />
          </box>
        ))}
      </box>
      <box height={1} paddingLeft={1} backgroundColor={BG}>
        <text fg={MUTE}>{more}</text>
      </box>
    </box>
  );
}

export function App() {
  const renderer = useRenderer();
  const [read, setRead] = useState<KitRead>(reading);
  const [pane, setPane] = useState(1);
  const [field, setField] = useState(0);
  const [shown, setShown] = useState(0);
  const [blink, setBlink] = useState(true);

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

  const panes = panesFor(read);
  const current = panes[pane] ?? panes[0];
  const group = GROUPS.find((item) => item === current.group) ?? null;
  const linesRef = useRef(current.lines.length);
  const countRef = useRef(panes.length);
  linesRef.current = current.lines.length;
  countRef.current = panes.length;

  useKeyboard((key: Key) => {
    const name = key.name ?? "";
    if (name === "q") {
      renderer.destroy();
      return;
    }
    if (name === "tab") {
      const step = key.shift ? -1 : 1;
      setPane((index) => (index + step + countRef.current) % countRef.current);
      setField(0);
      return;
    }
    if (name === "up" || name === "k") {
      setField((index) => Math.max(0, index - 1));
      return;
    }
    if (name === "down" || name === "j") {
      setField((index) => Math.min(linesRef.current - 1, index + 1));
    }
  });

  const reveal = read.detail.slice(0, shown);
  const row = (ids: string[]) =>
    ids.map((id) => panes.find((item) => item.id === id)).filter((item): item is PaneModel => Boolean(item));

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        <text fg={MUTE}>digichat</text>
        <text fg={INK}>  devkit</text>
        <text fg={MUTE}>{`  ${API}  `}</text>
        <text fg={SOFT}>{reveal}</text>
        {shown < read.detail.length && blink ? <text fg={INK}>█</text> : null}
      </box>
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        {GROUPS.map((item) => {
          const on = item === group;
          return (
            <text key={item} fg={on ? INK : MUTE}>
              {on ? `${GLYPH.user} ${item}   ` : `${GLYPH.system} ${item}   `}
            </text>
          );
        })}
      </box>
      <box flexGrow={1} flexDirection="column" backgroundColor={BG}>
        {[
          ["deployments", "identity", "features", "models"],
          ["appearance", "backend", "tools", "mcp"],
          ["gate", "preview", "export", "validation"],
        ].map((ids) => (
          <box key={ids.join()} flexGrow={1} flexDirection="row" backgroundColor={BG}>
            {row(ids).map((item) => (
              <PaneView
                key={item.id}
                pane={item}
                hot={item.id === current.id}
                field={field}
                caret={blink}
              />
            ))}
          </box>
        ))}
      </box>
      <box height={1} paddingLeft={1} flexDirection="row" backgroundColor={BG}>
        <text fg={MUTE}>{`tab pane   ↑↓ field   q quit   ${current.title}`}</text>
      </box>
    </box>
  );
}
