/**
 * Embed slash commands (#3418). Client-only: /lang, /help, /new never leave
 * the browser. /search and /docs force a locate tool with the user string as
 * the argument — the model is not hinted.
 */
export const LANG_CODES = ["en", "de", "it", "es", "fr"] as const;
export type LangCode = (typeof LANG_CODES)[number];

export type SlashId = "lang" | "help" | "new" | "search" | "docs";

export type SlashDef = {
  id: SlashId;
  names: readonly string[];
  needsArg: boolean;
  /** Public copy on the embed palette. */
  hint: string;
  forceTool?: "digisearch" | "digivault_search_notes";
};

export const SLASH_COMMANDS: readonly SlashDef[] = [
  {
    id: "search",
    names: ["/search", "/digisearch"],
    needsArg: true,
    hint: "Search the knowledge base",
    forceTool: "digisearch",
  },
  {
    id: "docs",
    names: ["/docs", "/digivault"],
    needsArg: true,
    hint: "Find original documents",
    forceTool: "digivault_search_notes",
  },
  {
    id: "lang",
    names: ["/lang"],
    needsArg: true,
    hint: "Switch language (en, de, it, es, fr)",
  },
  { id: "help", names: ["/help"], needsArg: false, hint: "Show commands" },
  { id: "new", names: ["/new"], needsArg: false, hint: "Start a new conversation" },
];

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

/** Palette rows while the composer holds a slash prefix and no argument yet. */
export function matchingSlashCommands(input: string): SlashDef[] {
  const q = input.trim().toLowerCase();
  if (!q.startsWith("/")) return [];
  if (/\s/.test(q)) return [];
  return SLASH_COMMANDS.filter((c) => c.names.some((n) => n.startsWith(q) || q.startsWith(n)));
}

export function slashHelpText(): string {
  return SLASH_COMMANDS.map((c) => `${c.names[0]} — ${c.hint}`).join("\n");
}

/** Display names kept in sync with digichat `LANGUAGES` / digigraph `LANGUAGE_NAMES`. */
export const LANG_LABELS: Record<LangCode, string> = {
  en: "English",
  de: "German",
  it: "Italian",
  es: "Spanish",
  fr: "French",
};

export function isLangCode(value: string): value is LangCode {
  return (LANG_CODES as readonly string[]).includes(value);
}
