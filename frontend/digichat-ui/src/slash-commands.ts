/**
 * Embed slash commands (#3418, #3511, #3556). Client-only: /lang, /help, /new,
 * /copy, /export, /websearch, /settings, /byok never leave the browser.
 * /search and /vault force a locate tool with the user string as the argument —
 * the model is not hinted.
 */
export const LANG_CODES = ["en", "de", "it", "es", "fr"] as const;
export type LangCode = (typeof LANG_CODES)[number];

export type SlashId =
  | "lang"
  | "help"
  | "new"
  | "search"
  | "vault"
  | "copy"
  | "export"
  | "websearch"
  | "settings"
  | "byok";

export type SlashDef = {
  id: SlashId;
  names: readonly string[];
  needsArg: boolean;
  /** Public copy on the embed palette. */
  hint: string;
  forceTool?: "digisearch" | "digivault_search_notes";
  /** When set, selecting the command opens a discrete Up/Down choice list. */
  choiceOptions?: readonly { value: string; label: string }[];
  /** Toggle commands flip state on Enter without an argument. */
  kind?: "toggle" | "action" | "force" | "client";
};

/** Display names kept in sync with digichat `LANGUAGES` / digigraph `LANGUAGE_NAMES`. */
export const LANG_LABELS: Record<LangCode, string> = {
  en: "English",
  de: "German",
  it: "Italian",
  es: "Spanish",
  fr: "French",
};

export const LANG_CHOICES: readonly { value: LangCode; label: string }[] = LANG_CODES.map(
  (code) => ({ value: code, label: LANG_LABELS[code] }),
);

export const SLASH_COMMANDS: readonly SlashDef[] = [
  {
    id: "search",
    names: ["/search", "/digisearch"],
    needsArg: true,
    hint: "Search the knowledge base",
    forceTool: "digisearch",
    kind: "force",
  },
  {
    id: "vault",
    names: ["/vault", "/docs", "/digivault"],
    needsArg: true,
    hint: "Vault",
    forceTool: "digivault_search_notes",
    kind: "force",
  },
  {
    id: "lang",
    names: ["/lang"],
    needsArg: true,
    hint: "Switch language (en, de, it, es, fr)",
    choiceOptions: LANG_CHOICES,
    kind: "client",
  },
  {
    id: "websearch",
    names: ["/websearch"],
    needsArg: false,
    hint: "Web search",
    kind: "toggle",
  },
  {
    id: "byok",
    names: ["/byok", "/key"],
    needsArg: false,
    hint: "BYOK",
    kind: "action",
  },
  {
    id: "settings",
    names: ["/settings"],
    needsArg: false,
    hint: "Settings",
    kind: "action",
  },
  {
    id: "copy",
    names: ["/copy"],
    needsArg: false,
    hint: "Copy last answer as markdown",
    kind: "client",
  },
  {
    id: "export",
    names: ["/export"],
    needsArg: false,
    hint: "Download thread as markdown",
    kind: "client",
  },
  { id: "help", names: ["/help"], needsArg: false, hint: "Show commands", kind: "client" },
  { id: "new", names: ["/new"], needsArg: false, hint: "Start a new conversation", kind: "client" },
];

export type SlashVisibility = {
  /** When false/undefined, /websearch is hidden from the palette. */
  webSearch?: boolean;
  /** When false, /byok is hidden. Default true when omitted. */
  byok?: boolean;
};

export type ParsedSlash =
  | { kind: "none" }
  | { kind: "incomplete"; command: SlashDef; prefix: string }
  | { kind: "command"; command: SlashDef; arg: string }
  | { kind: "unknown"; name: string };

export function parseSlashInput(raw: string): ParsedSlash {
  const text = raw.trim();
  if (!text.startsWith("/")) return { kind: "none" };
  const [name, ...rest] = text.split(/\s+/);
  const arg = rest.join(" ").trim();
  const needle = name.toLowerCase();
  const command = SLASH_COMMANDS.find((c) => c.names.some((n) => n === needle));
  if (!command) return { kind: "unknown", name };
  if (command.needsArg && !arg) {
    return { kind: "incomplete", command, prefix: `${command.names[0]} ` };
  }
  return { kind: "command", command, arg };
}

function isVisible(cmd: SlashDef, visibility?: SlashVisibility): boolean {
  if (cmd.id === "websearch") return visibility?.webSearch === true;
  if (cmd.id === "byok") return visibility?.byok !== false;
  return true;
}

/** Palette rows while the composer holds a slash prefix and no argument yet. */
export function matchingSlashCommands(
  input: string,
  visibility?: SlashVisibility,
): SlashDef[] {
  const q = input.trim().toLowerCase();
  if (!q.startsWith("/")) return [];
  if (/\s/.test(q)) return [];
  return SLASH_COMMANDS.filter(
    (c) =>
      isVisible(c, visibility) &&
      c.names.some((n) => n.startsWith(q) || q.startsWith(n)),
  );
}

export function slashHelpText(visibility?: SlashVisibility): string {
  return SLASH_COMMANDS.filter((c) => isVisible(c, visibility))
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
