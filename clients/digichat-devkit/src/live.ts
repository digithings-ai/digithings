import {
  activeEntry,
  fieldKey,
  isSecretLabel,
  panesFor,
  type FieldLine,
  type Overlay,
  type PaneModel,
} from "./present";
import { DASH, type KitRead } from "./read";

export type Draft = Overlay & { model: string | null };

export type ChatTurn = { id: string; role: "user" | "assistant" | "system"; text: string };

export type LiveTool = { id: string; label: string; on: boolean };
export type LiveMcp = { id: string; url: string; on: boolean };

export type LiveView = {
  headline: string;
  title: string | null;
  modelLine: string;
  activeModel: string | null;
  models: string[];
  placeholder: string | null;
  welcomeTitle: string | null;
  welcomeBody: string | null;
  suggestions: string[];
  accent: string | null;
  attachments: boolean;
  picker: boolean;
  alignRight: boolean;
  gate: string | null;
  chips: string[];
  tools: LiveTool[];
  mcp: LiveMcp[];
  issues: string[];
  configured: boolean;
};

export type SettingRow =
  | { kind: "group"; text: string }
  | { kind: "head"; text: string }
  | {
      kind: "field";
      pane: string;
      label: string;
      value: string;
      secret: boolean;
      toggle?: "flag" | "tool" | "mcp";
      id?: string;
    }
  | { kind: "mark"; text: string; on: boolean; id?: string; toggle?: "entry" };

export type StripRow =
  | { kind: "model"; value: string; choices: string[] }
  | { kind: "tool"; id: string; label: string; on: boolean }
  | { kind: "mcp"; id: string; label: string; on: boolean }
  | { kind: "empty"; slot: "tools" | "mcp"; text: "none" };

const HEX = /^#[0-9a-fA-F]{6}$/;
const CHIP_LABELS = ["attachments", "dictation", "speech", "sources", "model picker", "branch picker"];

const SIDE: Array<{ id: string; group: string }> = [
  { id: "deployments", group: "Deployments" },
  { id: "identity", group: "Basics" },
  { id: "features", group: "Basics" },
  { id: "models", group: "Basics" },
  { id: "appearance", group: "Appearance" },
  { id: "backend", group: "Advanced" },
  { id: "tools", group: "Advanced" },
  { id: "mcp", group: "Advanced" },
  { id: "gate", group: "Advanced" },
  { id: "export", group: "Export" },
  { id: "validation", group: "Validation" },
];

export function blankDraft(): Draft {
  return { entryId: null, values: {}, toolOn: {}, mcpOn: {}, model: null };
}

export function typeInto(draft: Draft, key: string, displayed: string, secret: boolean, ch: string): Draft {
  if (secret || isSecretLabel(key)) return draft;
  const cur = Object.prototype.hasOwnProperty.call(draft.values, key)
    ? draft.values[key]
    : displayed === DASH
      ? ""
      : displayed;
  return { ...draft, values: { ...draft.values, [key]: cur + ch } };
}

export function backspace(draft: Draft, key: string, displayed: string, secret: boolean): Draft {
  if (secret || isSecretLabel(key)) return draft;
  const cur = Object.prototype.hasOwnProperty.call(draft.values, key)
    ? draft.values[key]
    : displayed === DASH
      ? ""
      : displayed;
  return { ...draft, values: { ...draft.values, [key]: cur.slice(0, -1) } };
}

export function toggleFlag(draft: Draft, key: string, displayed: string): Draft {
  const next = displayed === "on" ? "off" : "on";
  return { ...draft, values: { ...draft.values, [key]: next } };
}

export function toggleTool(draft: Draft, id: string, on: boolean): Draft {
  return { ...draft, toolOn: { ...draft.toolOn, [id]: !on } };
}

export function toggleMcp(draft: Draft, id: string, on: boolean): Draft {
  return { ...draft, mcpOn: { ...draft.mcpOn, [id]: !on } };
}

export function selectEntry(id: string): Draft {
  return { entryId: id, values: {}, toolOn: {}, mcpOn: {}, model: null };
}

export function cycleModel(draft: Draft, choices: string[], displayed: string | null): Draft {
  const list = choices.filter((item) => item.length > 0);
  if (list.length === 0) return draft;
  const held = draft.model && list.includes(draft.model) ? draft.model : null;
  const shown = displayed && list.includes(displayed) ? displayed : null;
  const current = held ?? shown;
  const next = current == null ? list[0] : list[(list.indexOf(current) + 1) % list.length];
  return { ...draft, model: next, values: { ...draft.values, [fieldKey("models", "default model")]: next } };
}

function fieldOf(panes: PaneModel[], id: string, label: string): string {
  const pane = panes.find((item) => item.id === id);
  const line = pane?.lines.find((item) => item.kind === "field" && item.label === label);
  return line && line.kind === "field" ? line.value : DASH;
}

function shown(value: string): string | null {
  const text = value.trim();
  if (text === "" || text === DASH || text === "none" || text === "nothing to export") return null;
  return text;
}

function splitList(value: string): string[] {
  const text = shown(value);
  if (!text) return [];
  return text
    .split(" / ")
    .map((item) => item.trim())
    .filter((item) => item.length > 0 && item !== DASH && item !== "none");
}

function toolsOf(panes: PaneModel[]): LiveTool[] {
  const pane = panes.find((item) => item.id === "tools");
  if (!pane) return [];
  const tools: LiveTool[] = [];
  for (const line of pane.lines) {
    if (line.kind !== "field" || line.toggle !== "tool" || !line.id) continue;
    tools.push({
      id: line.id,
      label: line.label,
      on: line.value === "on" || line.value === "default on",
    });
  }
  return tools;
}

function mcpOf(panes: PaneModel[]): LiveMcp[] {
  const pane = panes.find((item) => item.id === "mcp");
  if (!pane) return [];
  const servers: LiveMcp[] = [];
  for (const line of pane.lines) {
    if (line.kind !== "field" || line.toggle !== "mcp" || !line.id) continue;
    const off = line.value.endsWith(" · off");
    const url = line.value.replace(/ · (on|off)$/, "");
    servers.push({ id: line.id, url, on: !off && url !== DASH });
  }
  return servers;
}

export type ChromeSlot = "title" | "headline" | "welcome" | "thread";

export type ChromeRow = { slot: ChromeSlot; text: string };

/** App chrome that stays on screen when a deployment is missing. Empty thread text is not a chat. */
export function mainChrome(view: LiveView, detail: string, turns: ChatTurn[]): ChromeRow[] {
  const rows: ChromeRow[] = [
    { slot: "title", text: view.title ?? DASH },
    { slot: "headline", text: view.headline },
    { slot: "welcome", text: view.welcomeTitle ?? DASH },
    { slot: "welcome", text: view.welcomeBody ?? DASH },
  ];
  if (turns.length === 0) {
    rows.push({ slot: "thread", text: view.configured ? "" : detail });
    return rows;
  }
  for (const turn of turns) rows.push({ slot: "thread", text: turn.text });
  return rows;
}

/** The configured app. Strings come from the selected deployment and local edits. */
export function liveFrom(read: KitRead, draft: Draft): LiveView {
  const panes = panesFor(read, draft);
  const entry = activeEntry(read, draft);
  const configured = entry?.deployment != null;
  const slug = shown(fieldOf(panes, "identity", "slug"));
  const skin = shown(fieldOf(panes, "appearance", "skin"));
  const theme = shown(fieldOf(panes, "appearance", "theme"));
  const headline = !slug && !skin && !theme ? DASH : `${slug ?? DASH} · ${skin ?? DASH} · ${theme ?? DASH}`;
  const model = shown(fieldOf(panes, "models", "default model"));
  const models = [...new Set([...(model ? [model] : []), ...splitList(fieldOf(panes, "models", "available models"))])];
  const activeModel = draft.model && models.includes(draft.model) ? draft.model : model;
  const accent = shown(fieldOf(panes, "appearance", "accent color"));
  const chips = CHIP_LABELS.filter((label) => fieldOf(panes, "features", label) === "on");
  const issues = (panes.find((pane) => pane.id === "validation")?.lines ?? [])
    .filter((line) => line.kind === "mark" && line.text !== "none")
    .map((line) => (line.kind === "mark" ? line.text : ""));
  return {
    headline,
    title: shown(fieldOf(panes, "appearance", "title")),
    modelLine: activeModel ?? (configured ? "no default model" : DASH),
    activeModel,
    models,
    placeholder: shown(fieldOf(panes, "appearance", "composer placeholder")),
    welcomeTitle: shown(fieldOf(panes, "appearance", "welcome title")),
    welcomeBody: shown(fieldOf(panes, "appearance", "welcome body")),
    suggestions: splitList(fieldOf(panes, "appearance", "starter suggestions")),
    accent: accent && HEX.test(accent) ? accent : null,
    attachments: fieldOf(panes, "features", "attachments") === "on",
    picker: fieldOf(panes, "features", "model picker") === "on" || fieldOf(panes, "models", "picker") === "on",
    alignRight: fieldOf(panes, "appearance", "user bubble alignment") === "right",
    gate: shown(fieldOf(panes, "gate", "mode")),
    chips,
    tools: toolsOf(panes),
    mcp: mcpOf(panes),
    issues,
    configured,
  };
}

export function rowsFor(read: KitRead, draft: Draft): SettingRow[] {
  const panes = panesFor(read, draft);
  const rows: SettingRow[] = [];
  let group = "";
  for (const spec of SIDE) {
    const pane = panes.find((item) => item.id === spec.id);
    if (!pane) continue;
    if (spec.group !== group) {
      group = spec.group;
      rows.push({ kind: "group", text: group });
    }
    if (pane.title !== group) rows.push({ kind: "head", text: pane.title });
    for (const line of pane.lines) {
      if (line.kind === "head") {
        rows.push({ kind: "head", text: line.text });
      } else if (line.kind === "mark") {
        rows.push({ kind: "mark", text: line.text, on: line.on, id: line.id, toggle: line.toggle });
      } else {
        rows.push(fieldRow(spec.id, line));
      }
    }
  }
  return rows;
}

function fieldRow(pane: string, line: FieldLine): SettingRow {
  return {
    kind: "field",
    pane,
    label: line.label,
    value: line.value,
    secret: line.secret === true || isSecretLabel(line.label),
    toggle: line.toggle,
    id: line.id,
  };
}

export function stripRows(view: LiveView): StripRow[] {
  const rows: StripRow[] = [{ kind: "model", value: view.modelLine, choices: view.models }];
  if (view.tools.length === 0) rows.push({ kind: "empty", slot: "tools", text: "none" });
  else {
    for (const tool of view.tools) rows.push({ kind: "tool", id: tool.id, label: tool.label, on: tool.on });
  }
  if (view.mcp.length === 0) rows.push({ kind: "empty", slot: "mcp", text: "none" });
  else {
    for (const server of view.mcp) rows.push({ kind: "mcp", id: server.id, label: server.id, on: server.on });
  }
  return rows;
}

export function activateStrip(draft: Draft, row: StripRow, view: LiveView): Draft {
  if (row.kind === "model") return cycleModel(draft, row.choices, view.activeModel);
  if (row.kind === "tool") return toggleTool(draft, row.id, row.on);
  if (row.kind === "mcp") return toggleMcp(draft, row.id, row.on);
  return draft;
}

/** Body for POST /api/baseline-chat. Omits secrets and system notes. */
export function chatBody(view: LiveView, history: ChatTurn[], text: string, id: string): Record<string, unknown> {
  const messages = [
    ...history
      .filter((turn) => turn.role === "user" || turn.role === "assistant")
      .map((turn) => ({
        id: turn.id,
        role: turn.role,
        parts: [{ type: "text", text: turn.text }],
      })),
    { id, role: "user", parts: [{ type: "text", text }] },
  ];
  const body: Record<string, unknown> = { messages };
  if (view.activeModel) body.model = view.activeModel;
  if (view.tools.length > 0) {
    body.tools = view.tools.map((tool) => ({ id: tool.id, enabled: tool.on }));
  }
  const mcp = view.mcp.filter((server) => server.on && server.url !== DASH);
  if (mcp.length > 0) {
    body.mcp = mcp.map((server) => ({ id: server.id, url: server.url }));
  }
  return body;
}

export function interpretBaseline(
  status: number,
  raw: string,
  contentType: string,
): { kind: "text"; text: string } | { kind: "error"; detail: string } {
  if (status < 200 || status >= 300) {
    const parsed = parseJson(raw);
    if (parsed && typeof parsed.error === "string" && parsed.error.length > 0) {
      return { kind: "error", detail: parsed.error };
    }
    return { kind: "error", detail: `baseline ${status}` };
  }
  if (contentType.includes("application/json")) {
    const parsed = parseJson(raw);
    if (!parsed) return { kind: "error", detail: "baseline unreadable" };
    if (typeof parsed.error === "string" && parsed.error.length > 0) {
      return { kind: "error", detail: parsed.error };
    }
    return { kind: "error", detail: "baseline empty" };
  }
  const deltas: string[] = [];
  for (const line of raw.split(/\r?\n/)) {
    const payload = line.startsWith("data:") ? line.slice(5).trim() : "";
    if (!payload || payload === "[DONE]") continue;
    const parsed = parseJson(payload);
    if (!parsed || parsed.type !== "text-delta") continue;
    const bit = parsed.delta ?? parsed.textDelta ?? parsed.text;
    if (typeof bit === "string" && bit.length > 0) deltas.push(bit);
  }
  if (deltas.length === 0) return { kind: "error", detail: "baseline empty" };
  return { kind: "text", text: deltas.join("") };
}

function parseJson(raw: string): Record<string, unknown> | null {
  try {
    const body = JSON.parse(raw) as unknown;
    if (typeof body === "object" && body !== null && !Array.isArray(body)) return body as Record<string, unknown>;
    return null;
  } catch {
    return null;
  }
}

export async function postBaseline(
  baseUrl: string,
  body: Record<string, unknown>,
  signal?: AbortSignal,
): Promise<{ kind: "text"; text: string } | { kind: "error"; detail: string }> {
  const root = baseUrl.replace(/\/+$/, "");
  try {
    const res = await fetch(`${root}/api/baseline-chat`, {
      method: "POST",
      signal,
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream, application/json",
        "x-digi-run-id": "devkit",
      },
      body: JSON.stringify(body),
    });
    const text = await res.text();
    return interpretBaseline(res.status, text, res.headers.get("content-type") ?? "");
  } catch {
    return { kind: "error", detail: "baseline unreachable" };
  }
}
