import { DASH, selectedEntry, type KitEntry, type KitRead } from "./read";

export type FieldLine = {
  kind: "field";
  label: string;
  value: string;
  secret?: boolean;
  id?: string;
  toggle?: "flag" | "tool" | "mcp";
};
export type MarkLine = { kind: "mark"; text: string; on: boolean; id?: string; toggle?: "entry" };
export type HeadLine = { kind: "head"; text: string };
export type Line = FieldLine | MarkLine | HeadLine;

export type PaneModel = {
  id: string;
  title: string;
  group: string;
  footer: string;
  lines: Line[];
};

const NONE = "none";
const NOTHING = "nothing to export";

/** Local edits. Secret fields ignore `values` and stay redacted. */
export type Overlay = {
  entryId: string | null;
  values: Record<string, string>;
  toolOn: Record<string, boolean>;
  mcpOn: Record<string, boolean>;
};

export function fieldKey(paneId: string, label: string): string {
  return `${paneId}:${label}`;
}

export function isSecretLabel(label: string): boolean {
  return label.includes("API key") || label.includes("consume URL");
}

function at(root: Record<string, unknown> | null, path: string[]): unknown {
  let cur: unknown = root;
  for (const key of path) {
    if (typeof cur !== "object" || cur === null || Array.isArray(cur)) return undefined;
    cur = (cur as Record<string, unknown>)[key];
  }
  return cur;
}

function has(root: Record<string, unknown> | null, path: string[]): boolean {
  let cur: unknown = root;
  for (let i = 0; i < path.length; i++) {
    if (typeof cur !== "object" || cur === null || Array.isArray(cur)) return false;
    const key = path[i];
    if (!Object.prototype.hasOwnProperty.call(cur, key)) return false;
    cur = (cur as Record<string, unknown>)[key];
  }
  return true;
}

function text(v: unknown): string {
  if (typeof v === "string" && v.trim() !== "") return v;
  if (typeof v === "number" && Number.isFinite(v)) return String(v);
  return DASH;
}

function flag(root: Record<string, unknown> | null, path: string[]): string {
  if (!has(root, path)) return DASH;
  const v = at(root, path);
  if (v === true) return "on";
  if (v === false) return "off";
  return DASH;
}

function field(label: string, value: string): FieldLine {
  return { kind: "field", label, value };
}

function flagField(label: string, value: string): FieldLine {
  return { kind: "field", label, value, toggle: "flag" };
}

/** Env-var names only. A raw credential stays "set" and is not printed. */
function envName(v: unknown): string {
  if (typeof v !== "string" || v.trim() === "") return DASH;
  if (/^[A-Z][A-Z0-9_]*$/.test(v)) return v;
  return "set";
}

const BACKEND_FIELDS: Record<string, Array<{ key: string; label: string; secret?: boolean }>> = {
  digigraph: [
    { key: "digisearchIndex", label: "digisearch index" },
    { key: "vaultPathPrefix", label: "vault path prefix" },
  ],
  foundry: [
    { key: "projectEndpoint", label: "project endpoint (https)" },
    { key: "agentName", label: "agent name" },
  ],
  "openai-completions": [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)", secret: true },
  ],
  "openai-responses": [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)", secret: true },
  ],
  anthropic: [
    { key: "model", label: "model" },
    { key: "apiKeyEnv", label: "API key env var (DIGICHAT_BACKEND_*)", secret: true },
  ],
  "google-vertex": [
    { key: "project", label: "GCP project" },
    { key: "location", label: "location" },
    { key: "model", label: "model" },
  ],
  langgraph: [
    { key: "apiUrl", label: "API URL (https)" },
    { key: "assistantId", label: "assistant id" },
    { key: "apiKeyEnv", label: "API key env var (optional)", secret: true },
  ],
  "ag-ui": [
    { key: "url", label: "URL (https)" },
    { key: "apiKeyEnv", label: "API key env var (optional)", secret: true },
  ],
  a2a: [
    { key: "baseUrl", label: "base URL (https)" },
    { key: "apiKeyEnv", label: "API key env var (optional)", secret: true },
  ],
};

function backendLines(dep: Record<string, unknown> | null): Line[] {
  const type = text(at(dep, ["backend", "type"]));
  const lines: Line[] = [
    field("backend type", type),
    field("persistence", text(at(dep, ["persistence"]))),
    field("auth", text(at(dep, ["auth"]))),
  ];
  for (const spec of BACKEND_FIELDS[type] ?? []) {
    const value = spec.secret ? envName(at(dep, ["backend", spec.key])) : text(at(dep, ["backend", spec.key]));
    lines.push({ kind: "field", label: spec.label, value, secret: spec.secret === true });
  }
  return lines;
}

function linesOf(dep: Record<string, unknown> | null): Record<string, Line[]> {
  const chrome = at(dep, ["chrome"]);
  const chromeRec = typeof chrome === "object" && chrome !== null && !Array.isArray(chrome)
    ? (chrome as Record<string, unknown>)
    : null;
  const welcome = at(dep, ["chrome", "welcome"]);
  const body = at(dep, ["chrome", "welcome", "body"]);
  const suggestions = at(dep, ["chrome", "suggestions"]);
  const available = at(dep, ["models", "available"]);
  const catalog = at(dep, ["tools", "catalog"]);
  const servers = at(dep, ["mcp", "servers"]);

  const welcomeBody = Array.isArray(body)
    ? body.filter((line): line is string => typeof line === "string" && line.length > 0).join(" / ")
    : typeof body === "string"
      ? body
      : DASH;

  const suggestionValue = Array.isArray(suggestions)
    ? suggestions.length === 0
      ? NONE
      : suggestions.filter((line): line is string => typeof line === "string").join(" / ")
    : DASH;

  const modelValue = Array.isArray(available)
    ? available.length === 0
      ? NONE
      : available.filter((line): line is string => typeof line === "string").join(" / ")
    : DASH;

  const toolLines: Line[] = [flagField("allow user toggle", flag(dep, ["tools", "allowUserToggle"]))];
  if (!Array.isArray(catalog) || catalog.length === 0) {
    toolLines.push({ kind: "mark", text: NONE, on: false });
  } else {
    for (const tool of catalog) {
      if (typeof tool !== "object" || tool === null) continue;
      const row = tool as Record<string, unknown>;
      const id = typeof row.id === "string" && row.id.length > 0 ? row.id : "";
      if (!id) continue;
      const label = typeof row.label === "string" && row.label.length > 0 ? row.label : id;
      const on = row.default === true ? "default on" : row.default === false ? "default off" : DASH;
      toolLines.push({ kind: "field", label, value: on, id, toggle: "tool" });
    }
  }

  const mcpLines: Line[] = [
    flagField("allow user servers", flag(dep, ["mcp", "allowUserServers"])),
    flagField("show add-server form", flag(dep, ["mcp", "allowAddForm"])),
  ];
  if (!Array.isArray(servers) || servers.length === 0) {
    mcpLines.push({ kind: "mark", text: NONE, on: false });
  } else {
    for (const server of servers) {
      if (typeof server !== "object" || server === null) continue;
      const row = server as Record<string, unknown>;
      const id = typeof row.id === "string" && row.id.length > 0 ? row.id : "";
      if (!id) continue;
      const url = typeof row.url === "string" && row.url.length > 0 ? row.url : DASH;
      mcpLines.push({ kind: "field", label: id, value: url, id, toggle: "mcp" });
    }
  }

  const consume = has(dep, ["gate", "consumeUrl"])
    ? text(at(dep, ["gate", "consumeUrl"])) === DASH
      ? "not set"
      : "set"
    : DASH;

  return {
    identity: [
      field("slug", text(at(dep, ["slug"]))),
      field(
        "aliases",
        Array.isArray(at(dep, ["aliases"]))
          ? (at(dep, ["aliases"]) as unknown[]).filter((item): item is string => typeof item === "string").join(", ") ||
            NONE
          : DASH,
      ),
    ],
    features: [
      flagField("attachments", flag(dep, ["features", "attachments"])),
      flagField("dictation", flag(dep, ["features", "dictation"])),
      flagField("speech", flag(dep, ["features", "speech"])),
      flagField("sources", flag(dep, ["features", "sources"])),
      flagField("model picker", flag(dep, ["features", "modelPicker"])),
      flagField("branch picker", flag(dep, ["features", "branchPicker"])),
      field("chain-of-thought view", text(at(dep, ["features", "view"]))),
      field("reasoning override", text(at(dep, ["features", "thinking"]))),
      field("page context", text(at(dep, ["features", "pageContext"]))),
    ],
    models: [
      field("default model", text(at(dep, ["models", "default"]))),
      field("available models", modelValue),
      flagField("picker", flag(dep, ["models", "allowPicker"])),
    ],
    appearance: [
      field("skin", text(chromeRec ? chromeRec.skin : undefined)),
      field("theme", text(chromeRec ? chromeRec.theme : undefined)),
      field("mode", text(chromeRec ? chromeRec.mode : undefined)),
      field("title", text(at(dep, ["chrome", "title"]))),
      field("welcome title", typeof welcome === "object" && welcome && "title" in welcome ? text((welcome as { title?: unknown }).title) : DASH),
      field("welcome body", has(dep, ["chrome", "welcome", "body"]) ? welcomeBody || NONE : DASH),
      field("composer placeholder", text(at(dep, ["chrome", "placeholder"]))),
      field("starter suggestions", has(dep, ["chrome", "suggestions"]) ? suggestionValue : DASH),
      field("accent color", text(at(dep, ["chrome", "accent", "color"]))),
      field("accent foreground", text(at(dep, ["chrome", "accent", "foreground"]))),
      flagField("attribution credit", flag(dep, ["chrome", "attribution"])),
      field("launcher mode", text(at(dep, ["chrome", "launcher", "mode"]))),
      field("launcher hotkey", text(at(dep, ["chrome", "launcher", "hotkey"]))),
      field("launcher label", text(at(dep, ["chrome", "launcher", "label"]))),
      field("reply language default", text(at(dep, ["chrome", "defaultLanguage"]))),
      field("user bubble alignment", text(at(dep, ["chrome", "transcript", "userAlign"]))),
    ],
    backend: backendLines(dep),
    tools: toolLines,
    mcp: mcpLines,
    gate: [
      field("mode", text(at(dep, ["gate", "mode"]))),
      field("activity detail", text(at(dep, ["gate", "activityDetail"]))),
      field("LLM access", text(at(dep, ["gate", "llmAccess"]))),
      { kind: "field", label: "quota consume URL (server-side)", value: consume, secret: true },
      field("locked contact", text(at(dep, ["gate", "lockedContact"]))),
      flagField("show BYOK", flag(dep, ["gate", "showByok"])),
      flagField("show language selector", flag(dep, ["gate", "showLanguageSelector"])),
      flagField("web search (legacy)", flag(dep, ["gate", "webSearch"])),
      field("minimum plan tier", text(at(dep, ["gate", "requiredPlanTier"]))),
    ],
  };
}

function deploymentLines(title: string, entries: KitEntry[], selected: KitEntry | null): Line[] {
  const lines: Line[] = [{ kind: "head", text: title }];
  if (entries.length === 0) {
    lines.push({ kind: "mark", text: NONE, on: false });
    return lines;
  }
  for (const entry of entries) {
    const invalid = entry.ok ? "" : " (invalid)";
    lines.push({
      kind: "mark",
      text: `${entry.label}${invalid}`,
      on: selected?.id === entry.id,
      id: entry.id,
      toggle: "entry",
    });
  }
  return lines;
}

export function activeEntry(read: KitRead, overlay?: Overlay): KitEntry | null {
  if (overlay?.entryId) {
    const hit = [...read.files, ...read.envs].find((entry) => entry.id === overlay.entryId);
    if (hit) return hit;
  }
  return selectedEntry(read);
}

function applyOverlay(paneId: string, lines: Line[], overlay?: Overlay): Line[] {
  if (!overlay) return lines;
  return lines.map((line) => {
    if (line.kind !== "field") return line;
    if (line.secret || isSecretLabel(line.label)) return line;
    const key = fieldKey(paneId, line.label);
    if (Object.prototype.hasOwnProperty.call(overlay.values, key)) {
      return { ...line, value: overlay.values[key] };
    }
    if (line.toggle === "tool" && line.id && Object.prototype.hasOwnProperty.call(overlay.toolOn, line.id)) {
      return { ...line, value: overlay.toolOn[line.id] ? "on" : "off" };
    }
    if (line.toggle === "mcp" && line.id && Object.prototype.hasOwnProperty.call(overlay.mcpOn, line.id)) {
      const suffix = overlay.mcpOn[line.id] ? "on" : "off";
      return { ...line, value: `${line.value} · ${suffix}` };
    }
    return line;
  });
}

/** Settings for one deployment. Values come from the configs read plus local edits. */
export function panesFor(read: KitRead, overlay?: Overlay): PaneModel[] {
  const selected = activeEntry(read, overlay);
  const dep = selected?.deployment ?? null;
  const sections = linesOf(dep);
  const issues = selected?.issues ?? [];
  const issueLines: Line[] =
    issues.length === 0
      ? [{ kind: "mark", text: NONE, on: false }]
      : issues.map((issue) => ({ kind: "mark" as const, text: issue, on: false }));

  return [
    {
      id: "deployments",
      title: "Deployments",
      group: "Local files",
      footer: "Local files · Environment tenants",
      lines: [
        ...deploymentLines("Local files", read.files, selected),
        ...deploymentLines("Environment tenants", read.envs, selected),
      ],
    },
    {
      id: "identity",
      title: "Identity",
      group: "Basics",
      footer: "Basics",
      lines: applyOverlay("identity", sections.identity, overlay),
    },
    {
      id: "features",
      title: "Features",
      group: "Basics",
      footer: "Basics",
      lines: applyOverlay("features", sections.features, overlay),
    },
    {
      id: "models",
      title: "Models",
      group: "Basics",
      footer: "Basics",
      lines: applyOverlay("models", sections.models, overlay),
    },
    {
      id: "appearance",
      title: "Appearance",
      group: "Appearance",
      footer: "Appearance",
      lines: applyOverlay("appearance", sections.appearance, overlay),
    },
    {
      id: "backend",
      title: "Backend",
      group: "Advanced",
      footer: "Advanced",
      lines: applyOverlay("backend", sections.backend, overlay),
    },
    {
      id: "tools",
      title: "Tools",
      group: "Advanced",
      footer: "Advanced",
      lines: applyOverlay("tools", sections.tools, overlay),
    },
    {
      id: "mcp",
      title: "MCP servers",
      group: "Advanced",
      footer: "Advanced",
      lines: applyOverlay("mcp", sections.mcp, overlay),
    },
    {
      id: "gate",
      title: "Gate",
      group: "Advanced",
      footer: "Advanced",
      lines: applyOverlay("gate", sections.gate, overlay),
    },
    {
      id: "export",
      title: "Export",
      group: "Export",
      footer: "Export",
      lines: [
        field("local compose", NOTHING),
        field("embed snippet", NOTHING),
        field("config YAML", selected?.redacted ? "redacted on file" : NOTHING),
      ],
    },
    {
      id: "validation",
      title: "Validation",
      group: "Validation",
      footer: issues.length === 0 ? NONE : `${issues.length}`,
      lines: issueLines,
    },
  ];
}

export const EMPTY_PHRASES = [NONE, NOTHING, DASH] as const;
