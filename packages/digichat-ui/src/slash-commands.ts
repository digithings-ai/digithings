/**
 * Product slash commands (#3418, #3511, #3556, #3733, #3736).
 * Client-only actions never leave the browser. A command that opens a pane
 * is one composer sequence (`/language English`); tools are toggled only
 * inside `/tools`, never as their own slash commands.
 */
import {
  TRACE_DENSITIES,
  TRACE_DENSITY_LABELS,
  type TraceDensity,
} from "@digithings/ui/chat/trace-spacing";

export const LANG_CODES = ["en", "nl", "it", "es", "fr"] as const;
export type LangCode = (typeof LANG_CODES)[number];

export type SlashCategory = "tools" | "session" | "actions" | "setup";

export type SlashId =
  | "lang"
  | "help"
  | "new"
  | "clear"
  | "copy"
  | "export"
  | "settings"
  | "byok"
  | "models"
  | "effort"
  | "search-engine"
  | "view"
  | "density"
  | "theme"
  | "thinking"
  | "sessions"
  | "compact"
  | "undo"
  | "redo"
  | "mcp"
  | "tools"
  | "artifacts";

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
   * Opens a submenu. The composer text is the sequence (`/theme dark`);
   * a second `/` filters that pane and does not open another palette.
   * Commands with `choiceOptions` are panes even when this is omitted.
   */
  pane?: boolean;
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

/** Web-search engine ids (digisearch provider vocabulary, #4724). */
export const SEARCH_ENGINE_CODES = [
  "auto",
  "internal",
  "exa",
  "tavily",
  "parallel",
  "firecrawl",
  "tinyfish",
] as const;
export type SearchEngineCode = (typeof SEARCH_ENGINE_CODES)[number];
export const SEARCH_ENGINE_CHOICES: readonly { value: SearchEngineCode; label: string }[] =
  SEARCH_ENGINE_CODES.map((code) => ({
    value: code,
    label: code === "auto" ? "Auto \u00b7 in-house" : code.charAt(0).toUpperCase() + code.slice(1),
  }));

export function isSearchEngine(value: string): value is SearchEngineCode {
  return (SEARCH_ENGINE_CODES as readonly string[]).includes(value.trim().toLowerCase());
}

export const VIEW_CODES = ["quiet", "balanced", "verbose"] as const;
export type ViewCode = (typeof VIEW_CODES)[number];
/**
 * The one home of the view-level wording. The composer menu's `/view` page
 * prints it beside each level, and the palette's `/view` choice list is built
 * from the same map, so the two surfaces name a level the same way. Keep it
 * exported: a second, private copy of this map is what let a rename drift and
 * leave one surface unlabelled (DIG-4665).
 *
 * The wording is the one the product prints today: `quiet` shows the titles
 * only, `balanced` opens the rows while they stream, `verbose` leaves
 * everything open. The retired `hidden` level has no entry: it folded into
 * `quiet` (#6079).
 */
export const VIEW_LABELS: Record<ViewCode, string> = {
  quiet: "Quiet \u00b7 titles only",
  balanced: "Balanced \u00b7 open while it runs",
  verbose: "Verbose \u00b7 everything open",
};
export const VIEW_CHOICES: readonly { value: ViewCode; label: string }[] = VIEW_CODES.map(
  (code) => ({ value: code, label: VIEW_LABELS[code] }),
);

export function isViewCode(value: string): value is ViewCode {
  return (VIEW_CODES as readonly string[]).includes(value.trim().toLowerCase());
}

export const DENSITY_CHOICES: readonly { value: TraceDensity; label: string }[] =
  TRACE_DENSITIES.map((code) => ({ value: code, label: TRACE_DENSITY_LABELS[code] }));

export const THINKING_CODES = ["auto", "collapsed", "open"] as const;
export type ThinkingCode = (typeof THINKING_CODES)[number];
export const THINKING_CHOICES: readonly { value: ThinkingCode; label: string }[] =
  THINKING_CODES.map((code) => ({ value: code, label: code.charAt(0).toUpperCase() + code.slice(1) }));

export function isThinkingCode(value: string): value is ThinkingCode {
  return (THINKING_CODES as readonly string[]).includes(value.trim().toLowerCase());
}

export const SLASH_CATEGORIES: readonly { id: SlashCategory; label: string }[] = [
  { id: "tools", label: "Tools" },
  { id: "session", label: "Session" },
  { id: "actions", label: "Actions" },
  { id: "setup", label: "Setup" },
];

export const SLASH_COMMANDS: readonly SlashDef[] = [
  {
    id: "mcp",
    names: ["/mcp"],
    needsArg: false,
    hint: "MCP JSON / auth / new",
    kind: "action",
    category: "tools",
    pane: true,
  },
  {
    id: "tools",
    names: ["/tools"],
    needsArg: false,
    hint: "Connected tools",
    kind: "action",
    category: "tools",
    pane: true,
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
    pane: true,
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
    id: "view",
    names: ["/view"],
    needsArg: false,
    hint: "quiet / balanced / verbose",
    choiceOptions: VIEW_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "density",
    names: ["/density"],
    needsArg: false,
    hint: "compact / default / airy",
    choiceOptions: DENSITY_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "theme",
    names: ["/theme"],
    needsArg: false,
    hint: "default dark, default light, then each palette",
    kind: "client",
    category: "setup",
    pane: true,
  },
  {
    id: "thinking",
    names: ["/thinking"],
    needsArg: false,
    hint: "auto / collapsed / open",
    choiceOptions: THINKING_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "search-engine",
    names: ["/search-engine"],
    needsArg: false,
    hint: "auto / exa / tavily / parallel / firecrawl / tinyfish",
    choiceOptions: SEARCH_ENGINE_CHOICES,
    kind: "client",
    category: "setup",
  },
  {
    id: "byok",
    names: ["/provider", "/byok", "/key"],
    needsArg: false,
    hint: "API provider",
    kind: "action",
    category: "setup",
    pane: true,
  },
  {
    id: "settings",
    names: ["/settings"],
    needsArg: false,
    hint: "Settings",
    kind: "action",
    category: "setup",
    pane: true,
  },
  {
    id: "toolbar",
    names: ["/toolbar"],
    needsArg: false,
    hint: "Composer toolbar",
    kind: "action",
    category: "setup",
  },
  {
    id: "scrollbar",
    names: ["/scrollbar"],
    needsArg: false,
    hint: "Scrollbars: always or on scroll",
    kind: "action",
    category: "setup",
  },
  {
    id: "artifacts",
    names: ["/artifacts"],
    needsArg: false,
    hint: "Files this session produced",
    kind: "action",
    category: "session",
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
    pane: true,
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
  /** Connected-tools palette. Hide when the install has no catalog/MCP. */
  tools?: boolean;
  /** Artifact list for this session. Hide where there is no artifact surface. */
  artifacts?: boolean;
  /** Colour theme. Hidden only when a host sets `themeLocked`; tenant embeds own the pick (`setTheme`). */
  theme?: boolean;
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
  if (cmd.id === "search-engine") return visibility?.webSearch === true;
  if (cmd.id === "byok") return visibility?.byok !== false;
  if (cmd.id === "sessions") return visibility?.sessions === true;
  if (cmd.id === "models" || cmd.id === "effort") return visibility?.models !== false;
  if (cmd.id === "mcp") return visibility?.mcp !== false;
  if (cmd.id === "tools") return visibility?.tools !== false;
  if (cmd.id === "artifacts") return visibility?.artifacts === true;
  if (cmd.id === "theme") return visibility?.theme !== false;
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

export function commandOpensPane(def: SlashDef): boolean {
  return def.pane === true || (def.choiceOptions?.length ?? 0) > 0;
}

const MENU_ID: Record<string, string> = { lang: "language", byok: "provider" };

/** Menu id for a command id. `lang` is the language pane; `byok` is provider. */
export function menuIdForCommand(id: string): string {
  return MENU_ID[id] ?? id;
}

export type PaletteKind = "closed" | "commands" | "pane";

export type PaletteFrame =
  | { kind: "closed" }
  | { kind: "commands"; filter: string }
  | { kind: "pane"; command: SlashDef; menu: string; filter: string };

/**
 * One composer string, one surface. A pane command plus a trailing space
 * (`/language `, `/language English`, `/language /`) is that pane. The same
 * token without the space is the parent command list, so backspacing out of
 * the sequence returns there. Anything else that starts with `/` is the
 * command list. A second palette is never a separate surface.
 */
export function paletteFrame(
  text: string,
  defs: readonly SlashDef[] = SLASH_COMMANDS,
): PaletteFrame {
  if (!text.startsWith("/") || text.includes("\n")) return { kind: "closed" };
  const match = /^\/(\S*)(.*)$/.exec(text);
  if (!match) return { kind: "closed" };
  const token = match[1] ?? "";
  const rest = match[2] ?? "";
  if (!token) return { kind: "commands", filter: "" };
  const needle = `/${token.toLowerCase()}`;
  const command = defs.find((def) => def.names.some((name) => name.toLowerCase() === needle));
  if (command && commandOpensPane(command) && rest.startsWith(" ")) {
    return {
      kind: "pane",
      command,
      menu: menuIdForCommand(command.id),
      filter: rest.slice(1),
    };
  }
  return { kind: "commands", filter: token.toLowerCase() };
}

/** Slash popover and menu are mutually exclusive. */
export function paletteSurfaces(
  text: string,
  defs: readonly SlashDef[] = SLASH_COMMANDS,
): { slash: boolean; menu: string | null } {
  const frame = paletteFrame(text, defs);
  if (frame.kind === "pane") return { slash: false, menu: frame.menu };
  if (frame.kind === "commands") return { slash: true, menu: null };
  return { slash: false, menu: null };
}

export type PaletteApply = {
  kind: PaletteKind;
  menu: "close" | "keep" | string;
  filter: string;
};

/**
 * Apply a frame on top of the previous one. A button-opened menu (settings)
 * stays while the composer is ordinary text. Leaving a pane closes it.
 */
export function applyPaletteFrame(
  prevKind: PaletteKind,
  frame: { kind: PaletteKind; menu?: string; filter?: string },
): PaletteApply {
  if (frame.kind === "pane" && frame.menu) {
    return { kind: "pane", menu: frame.menu, filter: frame.filter ?? "" };
  }
  if (frame.kind === "commands" || prevKind === "pane") {
    return {
      kind: frame.kind === "commands" ? "commands" : "closed",
      menu: "close",
      filter: "",
    };
  }
  return { kind: "closed", menu: "keep", filter: "" };
}

/** Composer draft written when a pane command is chosen: `/language `. */
export function paneDraftForId(
  id: string,
  defs: readonly SlashDef[] = SLASH_COMMANDS,
): string | null {
  const def = defs.find((command) => command.id === id || menuIdForCommand(command.id) === id);
  if (!def || !commandOpensPane(def)) return null;
  return `${def.names[0]} `;
}

/** Full sequence for an option: `/language English`. */
export function optionDraft(commandName: string, option: string): string {
  const name = commandName.startsWith("/") ? commandName : `/${commandName}`;
  const opt = option.trim();
  return opt ? `${name} ${opt}` : `${name} `;
}

export type SubmenuOption = {
  id: string;
  /** Text after the command that selects this row (`English`, `default dark`). */
  token: string;
  label?: string;
  aliases?: readonly string[];
};

/**
 * Filter a pane. An exact option token keeps the full list and highlights
 * that row, so the next arrow still moves. A partial query uses startsWith
 * on the token, id, label, and aliases.
 */
export function submenuRows<T extends SubmenuOption>(
  rows: readonly T[],
  filter: string,
): { rows: readonly T[]; cursor: number } {
  const q = filter.trim().toLowerCase();
  if (!q) return { rows, cursor: -1 };
  const exact = rows.findIndex((row) => optionKeys(row).includes(q));
  if (exact >= 0) return { rows, cursor: exact };
  const matched = rows.filter((row) =>
    [row.token, row.id, row.label ?? "", ...(row.aliases ?? [])].some((value) =>
      value.trim().toLowerCase().startsWith(q),
    ),
  );
  return { rows: matched, cursor: matched.length ? 0 : -1 };
}

function optionKeys(row: SubmenuOption): string[] {
  return [row.token, ...(row.aliases ?? [])]
    .map((value) => value.trim().toLowerCase())
    .filter((value) => value.length > 0);
}
