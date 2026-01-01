/**
 * Client applicator for digigraph session_* tools (#3736).
 * Same trust as slash — mutates EmbedChatPrefsApi only.
 */

import {
  isEffortCode,
  isSearchEngine,
} from "@digithings/digichat-ui";
import { asRecord } from "@digithings/ui/lib/record";
import type { EmbedChatPrefsApi } from "@digithings/ui/chat/stock";
import {
  MCP_ID_RE,
  connectedMcpConfigs,
  emptyMcpConfig,
  isMcpAuthKind,
  type SessionMcpConfig,
} from "@/components/stock/embed-mcp-flow";
import { tryResolveLanguageInput } from "@/lib/languages";
import {
  isLegacyViewMode,
  isThinkingMode,
  isViewMode,
  normalizeViewMode,
} from "@/lib/view-modes";
import { applyThemePick, currentThemeState } from "@/lib/product-slash-commands";
import { applyThemeModeKeepingPalette } from "@/lib/palette-prefs";
import { isTraceDensity } from "@digithings/ui/chat/trace-spacing";
import { isPaletteId, isThemePreference } from "@digithings/ui/theme";

export const SESSION_TOOL_NAMES = [
  "session_set_language",
  "session_set_model",
  "session_set_effort",
  "session_set_search_engine",
  "session_set_view",
  "session_set_thinking",
  "session_set_theme",
  "session_set_density",
  "session_toggle_tool",
  "session_upsert_mcp",
  "session_remove_mcp",
] as const;

export type SessionToolName = (typeof SESSION_TOOL_NAMES)[number];

export function isSessionToolName(name: string): name is SessionToolName {
  return (SESSION_TOOL_NAMES as readonly string[]).includes(name);
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
  const args = asRecord(rawArgs) ?? {};
  if (name === "session_set_language") {
    const code = tryResolveLanguageInput(str(args, "code", "language"));
    if (!code) return { ok: false, message: "Unknown language." };
    // setLanguage ignores a language the tenant does not offer; say so to the
    // model instead of reporting a switch that did not happen.
    const allowed = api.allowedLanguages;
    if (allowed?.length && !allowed.includes(code)) {
      return {
        ok: false,
        message: `This chat only answers in ${allowed.join(", ")}; the language was not changed.`,
      };
    }
    api.setLanguage(code);
    return { ok: true, message: `Language set to ${code}.` };
  }
  if (name === "session_set_model") {
    const raw = str(args, "model", "id");
    if (!raw) return { ok: false, message: "Missing model." };
    const model = resolveModelPick(raw, api.availableModels);
    if (!model) {
      return {
        ok: false,
        message: `Model ${raw} is not offered here. Choose one of: ${(api.availableModels ?? []).join(", ")}.`,
      };
    }
    api.setModel(model);
    return { ok: true, message: `Model set to ${model}. It applies from the next message.` };
  }
  if (name === "session_set_theme") {
    // Same path as `/theme`: a host-owned theme (embed) takes the pick, the
    // app paints the document theme and stores it like the palette does.
    if (api.themeLocked) return { ok: false, message: "The theme is fixed for this chat." };
    const mode = str(args, "mode", "theme", "preference").toLowerCase();
    const paletteRaw = str(args, "palette").toLowerCase();
    if (mode && !isThemePreference(mode)) {
      return { ok: false, message: "Theme mode must be light, dark, or auto." };
    }
    if (paletteRaw && paletteRaw !== "default" && !isPaletteId(paletteRaw)) {
      return { ok: false, message: `Unknown palette ${paletteRaw}.` };
    }
    if (!mode && !paletteRaw) return { ok: false, message: "Pass mode or palette." };
    const state = currentThemeState(api);
    if (mode && !paletteRaw && !api.setTheme) {
      applyThemeModeKeepingPalette(mode as "light" | "dark" | "auto");
    } else {
      applyThemePick(
        api,
        (mode || state.preference) as "light" | "dark" | "auto",
        paletteRaw || state.palette,
      );
    }
    return { ok: true, message: `Theme set to ${[paletteRaw, mode].filter(Boolean).join(" ")}.` };
  }
  if (name === "session_set_density") {
    const density = str(args, "density", "mode").toLowerCase();
    if (!isTraceDensity(density)) {
      return { ok: false, message: "Density must be compact, default, or airy." };
    }
    api.setDensity(density);
    return { ok: true, message: `Density set to ${density}.` };
  }
  if (name === "session_set_effort") {
    const effort = str(args, "effort").toLowerCase();
    if (!isEffortCode(effort)) return { ok: false, message: "Effort must be low, medium, or high." };
    api.setEffort(effort);
    return { ok: true, message: `Effort set to ${effort}.` };
  }
  if (name === "session_set_search_engine") {
    const engine = str(args, "engine", "search_engine", "provider").toLowerCase();
    if (!isSearchEngine(engine)) {
      return { ok: false, message: "Search engine must be auto, internal, exa, tavily, parallel, firecrawl, or tinyfish." };
    }
    api.setSearchEngine(engine);
    return { ok: true, message: `Search engine set to ${engine}.` };
  }
  if (name === "session_set_view") {
    const raw = str(args, "mode", "view").toLowerCase();
    // Retired ids (hidden / compact / detailed) fold forward, same as `/view`.
    const mode = isViewMode(raw) ? raw : isLegacyViewMode(raw) ? normalizeViewMode(raw) : null;
    if (!mode) {
      return { ok: false, message: "View must be quiet, balanced, or verbose." };
    }
    api.setView(mode);
    return { ok: true, message: `View set to ${mode}.` };
  }
  if (name === "session_set_thinking") {
    const mode = str(args, "mode", "thinking", "value").toLowerCase();
    if (isThinkingMode(mode)) {
      api.setThinking(mode);
      return { ok: true, message: `Thinking ${mode}.` };
    }
    // Back-compat with the boolean-era contract.
    const enabled = bool(args, "enabled") ?? bool(args, "thinking");
    if (enabled === undefined) {
      return { ok: false, message: "Thinking must be auto, collapsed, or open." };
    }
    api.setThinking(enabled ? "open" : "collapsed");
    return { ok: true, message: enabled ? "Thinking open." : "Thinking collapsed." };
  }
  if (name === "session_toggle_tool") {
    // /tools calls the setters itself. This model path must not flip a tool.
    if (api.toolControl === "agent" || api.toolControl === "locked") {
      return { ok: false, message: "Tools are locked for this host." };
    }
    return { ok: false, message: "Tools are changed in /tools." };
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
    const existing = connectedMcpConfigs(api.mcpServers, api.prefs.mcpCustom).find((s) => s.id === id);
    if (!api.allowUserMcp) {
      if (existing?.source !== "operator") {
        return { ok: false, message: "Session MCP is disabled." };
      }
      api.setMcpConfig(
        {
          ...existing,
          auth,
          token: str(args, "token") || existing.token,
        },
        existing.id,
      );
      return { ok: true, message: `Updated ${id}.` };
    }
    const next: SessionMcpConfig = {
      ...emptyMcpConfig(),
      id,
      label: str(args, "label") || id,
      url: str(args, "url"),
      auth,
      token: str(args, "token"),
      source: "session",
    };
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

/**
 * The model id a pick lands on, or null when the host offers a list and the
 * pick is not on it. Exact id, `preset:` token, case-insensitive id, or a
 * unique substring ("flash"). No list: the server allowlist decides.
 */
export function resolveModelPick(raw: string, available: readonly string[] | undefined): string | null {
  const pick = raw.trim();
  if (!pick) return null;
  if (!available?.length) return pick;
  if (pick.startsWith("preset:") || available.includes(pick)) return pick;
  const lower = pick.toLowerCase();
  const exact = available.find((id) => id.toLowerCase() === lower);
  if (exact) return exact;
  const partial = available.filter((id) => id.toLowerCase().includes(lower));
  return partial.length === 1 ? partial[0] : null;
}

export type ToolCallHit = {
  id: string;
  name: string;
  args: Record<string, unknown>;
  /** The server result arrived (the call finished). */
  done: boolean;
  /** The server refused (ok:false) or the call errored. */
  refused: boolean;
  /** Normalized values the server returned, when any. */
  prefs: Record<string, unknown> | null;
};

/** Unwrap the BFF tool output (`{...input, result}`) to digigraph's result. */
function serverResult(raw: unknown): Record<string, unknown> | null {
  const outer = asRecord(raw);
  if (!outer) return null;
  const inner = asRecord(outer.result);
  if (inner && ("ok" in inner || "session_prefs" in inner || "error" in inner)) return inner;
  return outer;
}

function toolNameFromType(type: string): string | null {
  if (type.startsWith("tool-session_")) return type.slice("tool-".length);
  return null;
}

/**
 * Walk assistant-ui / AI SDK message parts for session_* calls. Ids are
 * scoped by message: the stream numbers tool calls per turn (`tool-1`, …),
 * so a bare id repeats on every turn and later calls were skipped.
 */
export function sessionToolCallsFromMessages(messages: unknown[]): ToolCallHit[] {
  const out: ToolCallHit[] = [];
  for (const [index, msg] of messages.entries()) {
    const rec = asRecord(msg) ?? {};
    const role = rec.role;
    if (role && role !== "assistant") continue;
    const messageId = String(rec.id ?? index);
    const bags: unknown[] = [];
    if (Array.isArray(rec.parts)) bags.push(...rec.parts);
    if (Array.isArray(rec.content)) bags.push(...rec.content);
    for (const part of bags) {
      const p = asRecord(part) ?? {};
      const type = typeof p.type === "string" ? p.type : "";
      const named =
        (typeof p.toolName === "string" && p.toolName) ||
        (typeof p.name === "string" && p.name) ||
        toolNameFromType(type);
      if (!named || !isSessionToolName(named)) continue;
      const state = typeof p.state === "string" ? p.state : "";
      if (state === "partial-call" || state === "input-streaming") continue;
      const id = `${messageId}:${String(p.toolCallId ?? p.id ?? `${named}:${out.length}`)}`;
      const args = asRecord(p.input ?? p.args ?? p.arguments) ?? {};
      const output = p.result ?? p.output;
      const errored =
        p.isError === true || state === "output-error" || state === "output-denied";
      const done =
        errored || output !== undefined || state === "output-available" || state === "result";
      const res = serverResult(output);
      const refused = errored || res?.ok === false;
      const prefs = asRecord(res?.session_prefs) ?? null;
      out.push({ id, name: named, args, done, refused, prefs });
    }
  }
  return out;
}
