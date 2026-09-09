/**
 * Product slash commands (#3418, #3511, #3556, #3733, #3736).
 * Client-only actions never leave the browser. Catalog tools use one public
 * name with two gestures: empty = session toggle, remainder = force this send.
 */
export const LANG_CODES = ["en", "nl", "it", "es", "fr"] as const;
export type LangCode = (typeof LANG_CODES)[number];

export type SlashCategory = "tools" | "session" | "actions" | "setup";

export type SlashId =
  | "lang"
  | "help"
  | "new"
  | "clear"
  | "digisearch"
  | "digivault"
  | "copy"
  | "export"
  | "websearch"
  | "settings"
  | "byok"
  | "models"
  | "effort"
  | "thinking"
  | "sessions"
  | "compact"
  | "undo"
  | "redo"
  | "mcp"
  | "tools";

export type SlashDef = {
  id: SlashId | string;
  names: readonly string[];
  needsArg: boolean;
  /** Public copy on the embed palette. */
  hint: string;
  forceTool?: string;
  /** When set, selecting the command opens a discrete Up/Down choice list. */
  choiceOptions?: readonly { value: string; label: string }[];
  /**
   * tool — empty Enter toggles; with a query forces (or enables web search).
   * toggle — always flips, ignores extra words.
   */
  kind?: "toggle" | "action" | "tool" | "client";
  category?: SlashCategory;
};

/** Featured submenu labels. Full ISO map lives in digichat `languages.ts`. */
export const LANG_LABELS: Record<LangCode, string> = {
  en: "English",
  nl: "Dutch",
  it: "Italian",
  es: "Spanish",
  fr: "French",
};

export const LANG_CHOICES: readonly { value: LangCode; label: string }[] = LANG_CODES.map(
  (code) => ({ value: code, label: LANG_LABELS[code] }),
);

export const EFFORT_CODES = ["low", "medium", "high"] as const;
export type EffortCode = (typeof EFFORT_CODES)[number];
export const EFFORT_CHOICES: readonly { value: EffortCode; label: string }[] = EFFORT_CODES.map(
  (code) => ({ value: code, label: code }),
);

export function isEffortCode(value: string): value is EffortCode {
  return (EFFORT_CODES as readonly string[]).includes(value.trim().toLowerCase());
}

export const SLASH_CATEGORIES: readonly { id: SlashCategory; label: string }[] = [
  { id: "tools", label: "Tools" },
  { id: "session", label: "Session" },
  { id: "actions", label: "Actions" },
  { id: "setup", label: "Setup" },
];

export const SLASH_COMMANDS: readonly SlashDef[] = [
  {
    id: "digisearch",
    names: ["/digisearch"],
    needsArg: false,
    hint: "empty toggles, or /digisearch query",
    forceTool: "digisearch",
    kind: "tool",
    category: "tools",
  },
  {
    id: "digivault",
    names: ["/digivault"],
    needsArg: false,
    hint: "empty toggles, or /digivault query",
    forceTool: "digivault",
    kind: "tool",
    category: "tools",
  },
  {
    id: "websearch",
    names: ["/websearch"],
    needsArg: false,
    hint: "empty toggles, or /websearch query",
    forceTool: "web_search",
    kind: "tool",
    category: "tools",
  },
  {
    id: "mcp",
    names: ["/mcp"],
    needsArg: false,
    hint: "MCP JSON / auth / new",
    kind: "action",
    category: "tools",
  },
  {
    id: "tools",
    names: ["/tools"],
    needsArg: false,
    hint: "Connected tools",
    kind: "action",
    category: "tools",
  },
  {
    id: "lang",
    names: ["/language", "/lang"],
    needsArg: false,
    hint: "en / Italian / Italiano",
    choiceOptions: LANG_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "models",
    names: ["/models"],
    needsArg: false,
    hint: "Pick model",
    kind: "action",
    category: "setup",
  },
  {
    id: "effort",
    names: ["/effort"],
    needsArg: false,
    hint: "low / medium / high",
    choiceOptions: EFFORT_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "thinking",
    names: ["/thinking"],
    needsArg: false,
    hint: "Show or hide reasoning",
    kind: "toggle",
    category: "setup",
  },
  {
    id: "byok",
    names: ["/provider", "/byok", "/key"],
    needsArg: false,
    hint: "API provider",
    kind: "action",
    category: "setup",
  },
  {
    id: "settings",
    names: ["/settings"],
    needsArg: false,
    hint: "Settings",
    kind: "action",
    category: "setup",
  },
  {
    id: "sessions",
    names: ["/sessions", "/resume", "/continue"],
    needsArg: false,
    hint: "Switch conversation",
    kind: "action",
    category: "session",
  },
  {
    id: "new",
    names: ["/new"],
    needsArg: false,
    hint: "Start a new conversation",
    kind: "client",
    category: "session",
  },
  {
    id: "clear",
    names: ["/clear"],
    needsArg: false,
    hint: "New conversation (alias of /new)",
    kind: "client",
    category: "session",
  },
  {
    id: "compact",
    names: ["/compact", "/summarize"],
    needsArg: false,
    hint: "Summarize this thread to free context",
    kind: "client",
    category: "session",
  },
  {
    id: "undo",
    names: ["/undo"],
    needsArg: false,
    hint: "Previous assistant branch",
    kind: "client",
    category: "actions",
  },
  {
    id: "redo",
    names: ["/redo"],
    needsArg: false,
    hint: "Regenerate last answer",
    kind: "client",
    category: "actions",
  },
  {
    id: "copy",
    names: ["/copy"],
    needsArg: false,
    hint: "Copy last answer as markdown",
    kind: "client",
    category: "actions",
  },
  {
    id: "export",
    names: ["/export"],
    needsArg: false,
    hint: "Download thread as markdown",
    kind: "client",
    category: "actions",
  },
  {
    id: "help",
    names: ["/help"],
    needsArg: false,
    hint: "Show commands",
    kind: "client",
    category: "actions",
  },
];

export type SlashVisibility = {
  webSearch?: boolean;
  byok?: boolean;
  digisearch?: boolean;
  digivault?: boolean;
  /** Full-app thread list. Embed hides /sessions. */
  sessions?: boolean;
  models?: boolean;
  effort?: boolean;
  mcp?: boolean;
};

export type ParsedSlash =
  | { kind: "none" }
  | { kind: "incomplete"; command: SlashDef; prefix: string }
  | { kind: "command"; command: SlashDef; arg: string }
  | { kind: "unknown"; name: string };

function allDefs(extra?: readonly SlashDef[]): SlashDef[] {
  if (!extra?.length) return [...SLASH_COMMANDS];
  const seen = new Set(SLASH_COMMANDS.map((c) => c.id));
  return [...SLASH_COMMANDS, ...extra.filter((c) => !seen.has(c.id))];
}

export function parseSlashInput(raw: string, extra?: readonly SlashDef[]): ParsedSlash {
  const text = raw.trim();
  if (!text.startsWith("/")) return { kind: "none" };
  const [name, ...rest] = text.split(/\s+/);
  const arg = rest.join(" ").trim();
  const needle = name.toLowerCase();
  const command = allDefs(extra).find((c) => c.names.some((n) => n === needle));
  if (!command) return { kind: "unknown", name };
  if (command.needsArg && !arg) {
    return { kind: "incomplete", command, prefix: `${command.names[0]} ` };
  }
  return { kind: "command", command, arg };
}

function isVisible(cmd: SlashDef, visibility?: SlashVisibility): boolean {
  if (cmd.id === "websearch") return visibility?.webSearch === true;
  if (cmd.id === "byok") return visibility?.byok !== false;
  if (cmd.id === "digisearch") return visibility?.digisearch !== false;
  if (cmd.id === "digivault") return visibility?.digivault !== false;
  if (cmd.id === "sessions") return visibility?.sessions === true;
  if (cmd.id === "models" || cmd.id === "effort") return visibility?.models !== false;
  if (cmd.id === "mcp") return visibility?.mcp !== false;
  return true;
}

/** Palette rows while the composer holds a slash prefix and no argument yet. */
export function matchingSlashCommands(
  input: string,
  visibility?: SlashVisibility,
  extra?: readonly SlashDef[],
): SlashDef[] {
  const q = input.trim().toLowerCase();
  if (!q.startsWith("/")) return [];
  if (/\s/.test(q)) return [];
  return allDefs(extra).filter(
    (c) =>
      isVisible(c, visibility) &&
      c.names.some((n) => n.startsWith(q) || q.startsWith(n)),
  );
}

export function slashHelpText(
  visibility?: SlashVisibility,
  extra?: readonly SlashDef[],
): string {
  return allDefs(extra)
    .filter((c) => isVisible(c, visibility))
    .map((c) => `${c.names[0]} — ${c.hint}`)
    .join("\n");
}

export function isLangCode(value: string): value is LangCode {
  return (LANG_CODES as readonly string[]).includes(value);
}

/** Wrap palette highlight for Up/Down navigation. */
export function nextPaletteIndex(current: number, delta: number, length: number): number {
  if (length <= 0) return 0;
  return ((current + delta) % length + length) % length;
}

export type CliSettingRow =
  | {
      id: string;
      label: string;
      description: string;
      kind: "toggle";
      value: boolean;
    }
  | {
      id: string;
      label: string;
      description: string;
      kind: "choice";
      value: string;
      options: readonly { value: string; label: string }[];
    }
  | {
      id: string;
      label: string;
      description: string;
      kind: "action";
      actionLabel: string;
    };

export function formatCliSettingLine(row: CliSettingRow, selected: boolean): string {
  const mark = selected ? ">" : " ";
  if (row.kind === "toggle") {
    return `${mark} [${row.value ? "on" : "off"}] ${row.label} — ${row.description}`;
  }
  if (row.kind === "choice") {
    const current =
      row.options.find((o) => o.value === row.value)?.label ?? row.value;
    return `${mark} ${row.label}: ${current} — ${row.description}`;
  }
  return `${mark} ${row.label} → ${row.actionLabel} — ${row.description}`;
}

/** Extra catalog/MCP tool as a slash def (`/datatap` empty=toggle). */
export function catalogToolSlashDef(entry: {
  id: string;
  label?: string;
}): SlashDef {
  const id = entry.id.trim().toLowerCase();
  const label = entry.label?.trim() || id;
  return {
    id,
    names: [`/${id}`],
    needsArg: false,
    hint: `${label} — empty toggles, or /${id} query`,
    forceTool: id,
    kind: "tool",
    category: "tools",
  };
}
