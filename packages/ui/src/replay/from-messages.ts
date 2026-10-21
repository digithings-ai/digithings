/**
 * Turn stored UI messages (AI SDK parts, or the assistant-ui thread content
 * the palette reads) into a replay document. Secrets are removed here, before
 * any HTML is built.
 */

import { redactValue } from "./redact";
import type {
  ReplayAccent,
  ReplayChainItem,
  ReplayDocument,
  ReplayNotice,
  ReplayTheme,
  ReplayTool,
  ReplayToolStatus,
  ReplayTurn,
  ReplayView,
} from "./types";

export type ReplayChromeInput = {
  deployment: string;
  title?: string;
  welcome?: string;
  welcomeBody?: readonly string[];
  suggestions?: readonly string[];
  placeholder?: string;
  accent?: ReplayAccent | null;
  theme: ReplayTheme;
};

const TOOL_META = new Set([
  "tool-input-start",
  "tool-input-delta",
  "tool-input-available",
  "tool-output-available",
  "tool-output-error",
  "tool-approval-request",
  "tool-approval-response",
]);

const VIEWS = new Set<ReplayView>(["quiet", "balanced", "verbose"]);

export function messagesToReplay(
  messages: readonly unknown[],
  chrome: ReplayChromeInput,
  exportedAt: string,
): ReplayDocument {
  const turns = pairTurns(redactValue(messages));
  const theme = normalizeTheme(chrome.theme);
  const doc: ReplayDocument = {
    deployment: chrome.deployment.trim() || "digichat",
    title: chrome.title?.trim() || chrome.deployment.trim() || "digichat",
    welcome: chrome.welcome?.trim() ?? "",
    welcomeBody: (chrome.welcomeBody ?? []).map((line) => line.trim()).filter(Boolean),
    suggestions: (chrome.suggestions ?? []).map((line) => line.trim()).filter(Boolean),
    placeholder: chrome.placeholder?.trim() || "Message",
    accent: normalizeAccent(chrome.accent),
    theme,
    exportedAt,
    turns,
  };
  return redactValue(doc);
}

function normalizeTheme(theme: ReplayTheme): ReplayTheme {
  const resolved = theme.resolved === "light" ? "light" : "dark";
  const preference =
    theme.preference === "light" || theme.preference === "dark" || theme.preference === "auto"
      ? theme.preference
      : resolved;
  const palette = /^[a-z0-9-]+$/.test(theme.palette) ? theme.palette : "default";
  const view = VIEWS.has(theme.view) ? theme.view : "balanced";
  return { preference, resolved, palette, view };
}

function normalizeAccent(accent: ReplayAccent | null | undefined): ReplayAccent | null {
  if (!accent) return null;
  if (!/^#[0-9a-fA-F]{6}$/.test(accent.color)) return null;
  if (!/^#[0-9a-fA-F]{6}$/.test(accent.foreground)) return null;
  return { color: accent.color, foreground: accent.foreground };
}

function pairTurns(messages: readonly unknown[]): ReplayTurn[] {
  const turns: ReplayTurn[] = [];
  let current: ReplayTurn | null = null;
  messages.forEach((message, index) => {
    const role = roleOf(message);
    if (role === "user") {
      current = {
        id: idOf(message, index),
        userText: userText(message),
        blocks: [],
      };
      turns.push(current);
      return;
    }
    if (role !== "assistant" && role !== "tool") return;
    if (!current) {
      current = { id: idOf(message, index), userText: "", blocks: [] };
      turns.push(current);
    }
    appendParts(current, partsOf(message));
  });
  return turns.filter((turn) => turn.userText.trim() || turn.blocks.length > 0);
}

function appendParts(turn: ReplayTurn, parts: readonly unknown[]): void {
  let chain: ReplayChainItem[] = [];
  const flush = () => {
    if (chain.length === 0) return;
    turn.blocks.push({ kind: "chain", items: chain });
    chain = [];
  };
  for (const part of parts) {
    const item = chainItem(part);
    if (item) {
      chain.push(item);
      continue;
    }
    const text = textOf(part);
    if (text.trim()) {
      flush();
      turn.blocks.push({ kind: "text", markdown: text });
    }
  }
  flush();
}

function chainItem(part: unknown): ReplayChainItem | null {
  const record = asRecord(part);
  if (!record) return null;
  const type = stringOf(record.type);
  if (type === "reasoning") {
    const text = stringOf(record.text) || stringOf(record.reasoning);
    return text.trim() ? { kind: "reasoning", text } : null;
  }
  if (isTool(type)) return { kind: "tool", tool: toolOf(record, type) };
  const notice = noticeOf(record, type);
  return notice ? { kind: "notice", notice } : null;
}

function isTool(type: string): boolean {
  if (type === "tool-call" || type === "dynamic-tool") return true;
  if (!type.startsWith("tool-")) return false;
  return !TOOL_META.has(type);
}

function toolOf(record: Record<string, unknown>, type: string): ReplayTool {
  const name =
    stringOf(record.toolName) ||
    stringOf(record.name) ||
    (type.startsWith("tool-") && type !== "tool-call" ? type.slice("tool-".length) : "") ||
    "tool";
  const argsText = formatDump(record.argsText, record.args ?? record.input ?? record.rawInput);
  const status = toolStatus(record);
  const errorText =
    status === "error" || status === "cancelled" ? formatDump(undefined, record.errorText ?? record.error) : "";
  const resultText =
    status === "error" || status === "cancelled"
      ? ""
      : formatDump(undefined, record.result ?? record.output);
  return { name, argsText, resultText, status, errorText };
}

function toolStatus(record: Record<string, unknown>): ReplayToolStatus {
  if (record.isError === true) return "error";
  const state = stringOf(record.state);
  if (state === "output-error") return "error";
  if (state === "input-streaming" || state === "input-available") return "running";
  const status = asRecord(record.status);
  const statusType = status ? stringOf(status.type) : "";
  if (statusType === "incomplete") {
    return stringOf(status?.reason) === "cancelled" ? "cancelled" : "error";
  }
  if (statusType === "running") return "running";
  return "complete";
}

function noticeOf(record: Record<string, unknown>, type: string): ReplayNotice | null {
  const data = asRecord(record.data) ?? {};
  const name = stringOf(record.name);
  const dataName = type.startsWith("data-") ? type.slice("data-".length) : name;
  if (type !== "data" && !type.startsWith("data-")) return null;
  if (dataName !== "notice" && dataName !== "status" && dataName !== "connection") return null;
  if (dataName === "connection") {
    const state = stringOf(data.state);
    if (state === "connected" || state === "ready") return null;
  }
  const title = stringOf(data.message) || stringOf(data.title);
  if (!title.trim()) return null;
  const detail = stringOf(data.detail);
  return {
    tone: data.tone === "error" ? "error" : "status",
    title,
    detail,
  };
}

function userText(message: unknown): string {
  const record = asRecord(message);
  if (!record) return "";
  if (typeof record.content === "string") return record.content;
  return partsOf(message)
    .map((part) => {
      const item = asRecord(part);
      if (!item || stringOf(item.type) !== "text") return "";
      return stringOf(item.text);
    })
    .filter(Boolean)
    .join("");
}

function textOf(part: unknown): string {
  const record = asRecord(part);
  if (!record || stringOf(record.type) !== "text") return "";
  return stringOf(record.text);
}

function partsOf(message: unknown): unknown[] {
  const record = asRecord(message);
  if (!record) return [];
  if (Array.isArray(record.parts)) return record.parts;
  if (Array.isArray(record.content)) return record.content;
  if (typeof record.content === "string") return [{ type: "text", text: record.content }];
  return [];
}

function roleOf(message: unknown): string {
  return stringOf(asRecord(message)?.role);
}

function idOf(message: unknown, index: number): string {
  const id = stringOf(asRecord(message)?.id);
  return id || `turn-${index + 1}`;
}

function formatDump(raw: unknown, value: unknown): string {
  if (typeof raw === "string" && raw.trim()) {
    const parsed = tryParse(raw);
    return parsed === undefined ? raw : pretty(redactValue(parsed));
  }
  if (value == null || value === "") return "";
  if (typeof value === "string") {
    const parsed = tryParse(value);
    return parsed === undefined ? value : pretty(redactValue(parsed));
  }
  return pretty(redactValue(value));
}

function tryParse(value: string): unknown {
  try {
    return JSON.parse(value);
  } catch {
    return undefined;
  }
}

function pretty(value: unknown): string {
  try {
    return JSON.stringify(value, null, 2) ?? "";
  } catch {
    return "";
  }
}

function asRecord(value: unknown): Record<string, unknown> | null {
  if (!value || typeof value !== "object" || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function stringOf(value: unknown): string {
  return typeof value === "string" ? value : "";
}
