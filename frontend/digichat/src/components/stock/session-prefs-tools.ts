/**
 * Client applicator for digigraph session_* tools (#3736).
 * Same trust as slash — mutates EmbedChatPrefsApi only.
 */

import {
  isEffortCode,
} from "@digithings/digichat-ui";
import type { EmbedChatPrefsApi } from "@/components/stock/embed-chat-prefs";
import {
  MCP_ID_RE,
  connectedMcpConfigs,
  emptyMcpConfig,
  isMcpAuthKind,
  type SessionMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import { tryResolveLanguageInput } from "@/lib/languages";

export const SESSION_TOOL_NAMES = [
  "session_set_language",
  "session_set_model",
  "session_set_effort",
  "session_set_thinking",
  "session_toggle_tool",
  "session_upsert_mcp",
  "session_remove_mcp",
] as const;

export type SessionToolName = (typeof SESSION_TOOL_NAMES)[number];

export function isSessionToolName(name: string): name is SessionToolName {
  return (SESSION_TOOL_NAMES as readonly string[]).includes(name);
}

function asRecord(value: unknown): Record<string, unknown> {
  return value && typeof value === "object" && !Array.isArray(value)
    ? (value as Record<string, unknown>)
    : {};
}

function str(args: Record<string, unknown>, ...keys: string[]): string {
  for (const k of keys) {
    const v = args[k];
    if (typeof v === "string" && v.trim()) return v.trim();
  }
  return "";
}

function bool(args: Record<string, unknown>, key: string): boolean | undefined {
  const v = args[key];
  if (typeof v === "boolean") return v;
  if (v === "true" || v === "1") return true;
  if (v === "false" || v === "0") return false;
  return undefined;
}

export type ApplySessionToolResult = {
  ok: boolean;
  message: string;
  pending?: boolean;
};

export function applySessionTool(
  name: string,
  rawArgs: unknown,
  api: EmbedChatPrefsApi,
): ApplySessionToolResult {
  const args = asRecord(rawArgs);
  if (name === "session_set_language") {
    const code = tryResolveLanguageInput(str(args, "code", "language"));
    if (!code) return { ok: false, message: "Unknown language." };
    api.setLanguage(code);
    return { ok: true, message: `Language set to ${code}.` };
  }
  if (name === "session_set_model") {
    const model = str(args, "model", "id");
    if (!model) return { ok: false, message: "Missing model." };
    api.setModel(model);
    return { ok: true, message: `Model set to ${model}.` };
  }
  if (name === "session_set_effort") {
    const effort = str(args, "effort").toLowerCase();
    if (!isEffortCode(effort)) return { ok: false, message: "Effort must be low, medium, or high." };
    api.setEffort(effort);
    return { ok: true, message: `Effort set to ${effort}.` };
  }
  if (name === "session_set_thinking") {
    const enabled = bool(args, "enabled") ?? bool(args, "thinking");
    if (enabled === undefined) return { ok: false, message: "Missing enabled." };
    api.setThinking(enabled);
    return { ok: true, message: enabled ? "Thinking on." : "Thinking off." };
  }
  if (name === "session_toggle_tool") {
    const id = str(args, "id", "tool").toLowerCase();
    const enabled = bool(args, "enabled");
    if (!id || enabled === undefined) return { ok: false, message: "Need id and enabled." };
    if (id === "digisearch") api.setDigisearch(enabled);
    else if (id === "digivault") api.setVault(enabled);
    else if (id === "websearch" || id === "web_search") api.setWebSearch(enabled);
    else api.setExtraTool(id, enabled);
    return { ok: true, message: `${id} ${enabled ? "on" : "off"}.` };
  }
  if (name === "session_remove_mcp") {
    const id = str(args, "id").toLowerCase();
    if (!MCP_ID_RE.test(id)) return { ok: false, message: "Invalid MCP id." };
    api.removeMcpConfig(id);
    return { ok: true, message: `Removed ${id}.` };
  }
  if (name === "session_upsert_mcp") {
    const id = str(args, "id").toLowerCase();
    if (!MCP_ID_RE.test(id)) return { ok: false, message: "id must be a lowercase slug." };
    const authRaw = str(args, "auth").toLowerCase() || "none";
    const auth = isMcpAuthKind(authRaw) ? authRaw : "none";
    const next: SessionMcpConfig = {
      ...emptyMcpConfig(),
      id,
      label: str(args, "label") || id,
      url: str(args, "url"),
      auth,
      token: str(args, "token"),
      source: "session",
    };
    const existing = connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom).find((s) => s.id === id);
    const newUrl = next.url && next.url !== (existing?.url ?? "");
    api.setMcpConfig(next, existing?.source === "session" ? existing.id : id);
    if (newUrl) {
      api.openMcp(id);
      return { ok: true, pending: true, message: `Added ${id}. Confirm in /mcp.` };
    }
    return { ok: true, message: `Updated ${id}.` };
  }
  return { ok: false, message: `Unknown session tool ${name}.` };
}

type ToolCallHit = { id: string; name: string; args: Record<string, unknown> };

function toolNameFromType(type: string): string | null {
  if (type.startsWith("tool-session_")) return type.slice("tool-".length);
  return null;
}

/** Walk assistant-ui / AI SDK message parts for completed session_* calls. */
export function sessionToolCallsFromMessages(messages: unknown[]): ToolCallHit[] {
  const out: ToolCallHit[] = [];
  for (const msg of messages) {
    const rec = asRecord(msg);
    const role = rec.role;
    if (role && role !== "assistant") continue;
    const bags: unknown[] = [];
    if (Array.isArray(rec.parts)) bags.push(...rec.parts);
    if (Array.isArray(rec.content)) bags.push(...rec.content);
    for (const part of bags) {
      const p = asRecord(part);
      const type = typeof p.type === "string" ? p.type : "";
      const named =
        (typeof p.toolName === "string" && p.toolName) ||
        (typeof p.name === "string" && p.name) ||
        toolNameFromType(type);
      if (!named || !isSessionToolName(named)) continue;
      const state = typeof p.state === "string" ? p.state : "";
      if (state && state !== "output-available" && state !== "result" && state !== "complete") {
        if (state === "partial-call" || state === "input-streaming") continue;
      }
      const id = String(p.toolCallId ?? p.id ?? `${named}:${out.length}`);
      const args = asRecord(p.input ?? p.args ?? p.arguments);
      out.push({ id, name: named, args });
    }
  }
  return out;
}
