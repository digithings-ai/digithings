/**
 * Slash palette for the digichat thread. Same commands as
 * packages/digichat-ui slash-commands.ts. Picks stay in this client:
 * the official chat route accepts `{ text }` only.
 */

export type ChatPrefs = {
  webSearch: boolean;
  digisearch: boolean;
  digivault: boolean;
  view: "hidden" | "compact" | "balanced" | "detailed";
  thinking: "auto" | "collapsed" | "open";
  language: "en" | "nl" | "it" | "es" | "fr";
  effort: "low" | "medium" | "high";
  searchEngine: "auto" | "internal" | "exa" | "tavily" | "parallel" | "firecrawl" | "tinyfish";
  provider: string;
  model: string;
};

export const DEFAULT_PREFS: ChatPrefs = {
  webSearch: false,
  digisearch: false,
  digivault: false,
  view: "compact",
  thinking: "auto",
  language: "en",
  effort: "medium",
  searchEngine: "auto",
  provider: "",
  model: "",
};

export const PROVIDERS = ["openrouter", "openai", "anthropic", "gemini", "xai"] as const;

const LANGS: readonly { id: ChatPrefs["language"]; label: string }[] = [
  { id: "en", label: "English" },
  { id: "nl", label: "Dutch" },
  { id: "it", label: "Italian" },
  { id: "es", label: "Spanish" },
  { id: "fr", label: "French" },
];

const VIEWS: readonly { value: ChatPrefs["view"]; label: string }[] = [
  { value: "hidden", label: "Hidden · answer only" },
  { value: "compact", label: "Compact · closed" },
  { value: "balanced", label: "Balanced · collapse when done" },
  { value: "detailed", label: "Detailed · stays open" },
];

const THINKING: readonly { value: ChatPrefs["thinking"]; label: string }[] = [
  { value: "auto", label: "Auto" },
  { value: "collapsed", label: "Collapsed" },
  { value: "open", label: "Open" },
];

const EFFORT: readonly { value: ChatPrefs["effort"]; label: string }[] = [
  { value: "low", label: "low" },
  { value: "medium", label: "medium" },
  { value: "high", label: "high" },
];

const ENGINES: readonly { value: ChatPrefs["searchEngine"]; label: string }[] = [
  { value: "auto", label: "Auto · in-house" },
  { value: "internal", label: "Internal" },
  { value: "exa", label: "Exa" },
  { value: "tavily", label: "Tavily" },
  { value: "parallel", label: "Parallel" },
  { value: "firecrawl", label: "Firecrawl" },
  { value: "tinyfish", label: "Tinyfish" },
];

type Kind = "tool" | "choice" | "action";

type Command = {
  id: string;
  names: readonly string[];
  hint: string;
  kind: Kind;
};

const COMMANDS: readonly Command[] = [
  { id: "digisearch", names: ["/digisearch"], hint: "empty toggles, or /digisearch query", kind: "tool" },
  { id: "digivault", names: ["/digivault"], hint: "empty toggles, or /digivault query", kind: "tool" },
  { id: "websearch", names: ["/websearch"], hint: "empty toggles, or /websearch query", kind: "tool" },
  { id: "mcp", names: ["/mcp"], hint: "MCP JSON / auth / new", kind: "action" },
  { id: "tools", names: ["/tools"], hint: "Connected tools", kind: "action" },
  { id: "lang", names: ["/language", "/lang"], hint: "en / Italian / Italiano", kind: "choice" },
  { id: "models", names: ["/models"], hint: "Pick model", kind: "action" },
  { id: "effort", names: ["/effort"], hint: "low / medium / high", kind: "choice" },
  { id: "view", names: ["/view"], hint: "hidden / compact / balanced / detailed", kind: "choice" },
  { id: "thinking", names: ["/thinking"], hint: "auto / collapsed / open", kind: "choice" },
  { id: "search-engine", names: ["/search-engine"], hint: "auto / exa / tavily / parallel / firecrawl / tinyfish", kind: "choice" },
  { id: "byok", names: ["/provider", "/byok", "/key"], hint: "API provider", kind: "action" },
  { id: "settings", names: ["/settings"], hint: "Settings", kind: "action" },
  { id: "sessions", names: ["/sessions", "/resume", "/continue"], hint: "Switch conversation", kind: "action" },
  { id: "new", names: ["/new"], hint: "Start a new conversation", kind: "action" },
  { id: "clear", names: ["/clear"], hint: "New conversation (alias of /new)", kind: "action" },
  { id: "compact", names: ["/compact", "/summarize"], hint: "Summarize this thread to free context", kind: "action" },
  { id: "undo", names: ["/undo"], hint: "Previous assistant branch", kind: "action" },
  { id: "redo", names: ["/redo"], hint: "Regenerate last answer", kind: "action" },
  { id: "copy", names: ["/copy"], hint: "Copy last answer as markdown", kind: "action" },
  { id: "export", names: ["/export"], hint: "Download thread as markdown", kind: "action" },
  { id: "charts", names: ["/charts"], hint: "Open charts in the DigiChat web UI", kind: "action" },
  { id: "help", names: ["/help"], hint: "Show commands", kind: "action" },
];

export type PaletteRow = { id: string; label: string; description: string };

export type Pane = "settings" | "models" | "provider" | "mcp" | "tools" | "help" | "more" | "export";

export type CommandResult =
  | { type: "draft"; draft: string; note: string }
  | { type: "prefs"; prefs: ChatPrefs; note: string }
  | { type: "choices"; id: string; note: string }
  | { type: "pane"; pane: Pane; note: string }
  | { type: "new-session"; note: string }
  | { type: "sessions"; note: string }
  | { type: "copy"; note: string }
  | { type: "export"; note: string }
  | { type: "redo"; note: string }
  | { type: "send"; text: string; note: string }
  | { type: "note"; note: string }
  | { type: "block"; note: string };

const onOff = (on: boolean, onText: string, offText: string) => (on ? `On · ${onText}` : `Off · ${offText}`);

function languageLabel(code: string): string {
  return LANGS.find((row) => row.id === code)?.label ?? code;
}

function hintFor(command: Command, prefs: ChatPrefs): string {
  if (command.id === "websearch") return onOff(prefs.webSearch, "External cites", "corpus only");
  if (command.id === "digisearch") return onOff(prefs.digisearch, "knowledge base", "disabled this session");
  if (command.id === "digivault") return onOff(prefs.digivault, "vault notes", "disabled this session");
  if (command.id === "view") return `View: ${prefs.view}`;
  if (command.id === "thinking") return `Thinking: ${prefs.thinking}`;
  if (command.id === "lang") return `Reply language (${languageLabel(prefs.language)})`;
  if (command.id === "models") return prefs.model || command.hint;
  if (command.id === "effort") return prefs.effort;
  if (command.id === "search-engine") return prefs.searchEngine || "auto";
  return command.hint;
}

function languageRows(): PaletteRow[] {
  return LANGS.map((row) => ({
    id: `lang:${row.id}`,
    label: `/${row.label.toLowerCase()}`,
    description: `Reply in ${row.label}`,
  }));
}

function allRows(prefs: ChatPrefs): PaletteRow[] {
  const commands = COMMANDS.map((command) => ({
    id: command.id,
    label: command.names[0] ?? command.id,
    description: hintFor(command, prefs),
  }));
  return [...commands, ...languageRows()];
}

/** Flat list while the draft is a slash prefix. A trailing space closes it. */
export function paletteRows(draft: string, prefs: ChatPrefs): PaletteRow[] {
  if (draft.endsWith(" ")) return [];
  const query = draft.trim().toLowerCase();
  if (!query.startsWith("/") || /\s/.test(query)) return [];
  return allRows(prefs).filter((row) => {
    const label = row.label.toLowerCase();
    return label.startsWith(query) || query.startsWith(label);
  });
}

export function mentionQuery(draft: string): string | null {
  const match = draft.match(/(^|\s)@([^\s]*)$/);
  if (!match) return null;
  return match[2] ?? "";
}

export function mentionRows(draft: string, names: readonly string[]): PaletteRow[] {
  const query = mentionQuery(draft);
  if (query === null) return [];
  const needle = query.toLowerCase();
  return names
    .filter((name, index) => name && names.indexOf(name) === index && name.toLowerCase().startsWith(needle))
    .map((name) => ({ id: name, label: `@${name}`, description: "tool" }));
}

export function insertMention(draft: string, name: string): string {
  return draft.replace(/(^|\s)@[^\s]*$/, `$1@${name} `);
}

function commandById(id: string): Command | undefined {
  return COMMANDS.find((command) => command.id === id);
}

function languageId(token: string): ChatPrefs["language"] | null {
  const name = token.replace(/^\//, "").toLowerCase();
  const hit = LANGS.find((row) => row.id === name || row.label.toLowerCase() === name);
  return hit?.id ?? null;
}

function findCommand(token: string): Command | undefined {
  const needle = token.toLowerCase();
  return COMMANDS.find((command) => command.names.some((name) => name === needle));
}

function withPrefs(prefs: ChatPrefs, note: string): CommandResult {
  return { type: "prefs", prefs, note };
}

function toggleTool(id: "websearch" | "digisearch" | "digivault", prefs: ChatPrefs): CommandResult {
  if (id === "websearch") {
    const webSearch = !prefs.webSearch;
    return withPrefs({ ...prefs, webSearch }, webSearch ? "web search on" : "web search off");
  }
  if (id === "digisearch") {
    const digisearch = !prefs.digisearch;
    return withPrefs({ ...prefs, digisearch }, digisearch ? "digisearch on" : "digisearch off");
  }
  const digivault = !prefs.digivault;
  return withPrefs({ ...prefs, digivault }, digivault ? "digivault on" : "digivault off");
}

export function choiceOptions(id: string, prefs: ChatPrefs): { value: string; label: string }[] {
  if (id === "lang") return LANGS.map((row) => ({ value: row.id, label: row.label }));
  if (id === "view") return VIEWS.map((row) => ({ value: row.value, label: row.label }));
  if (id === "thinking") return THINKING.map((row) => ({ value: row.value, label: row.label }));
  if (id === "effort") return EFFORT.map((row) => ({ value: row.value, label: row.label }));
  if (id === "search-engine") return ENGINES.map((row) => ({ value: row.value, label: row.label }));
  return [];
}

export function applyChoice(id: string, value: string, prefs: ChatPrefs): CommandResult {
  const allowed = choiceOptions(id, prefs).some((row) => row.value === value);
  if (!allowed) return { type: "note", note: "" };
  if (id === "lang" && languageId(value)) return withPrefs({ ...prefs, language: languageId(value)! }, `language ${languageLabel(value)}`);
  if (id === "view") return withPrefs({ ...prefs, view: value as ChatPrefs["view"] }, `view ${value}`);
  if (id === "thinking") return withPrefs({ ...prefs, thinking: value as ChatPrefs["thinking"] }, `thinking ${value}`);
  if (id === "effort") return withPrefs({ ...prefs, effort: value as ChatPrefs["effort"] }, `effort ${value}`);
  if (id === "search-engine") {
    return withPrefs({ ...prefs, searchEngine: value as ChatPrefs["searchEngine"] }, `search ${value}`);
  }
  return { type: "note", note: "" };
}

/** Palette highlight runs the command, or inserts a tool draft so a query can follow. */
export function pickPalette(id: string, prefs: ChatPrefs): CommandResult {
  if (id.startsWith("lang:")) {
    const code = id.slice(5);
    return applyChoice("lang", code, prefs);
  }
  const command = commandById(id);
  if (!command) return { type: "block", note: "unknown command" };
  if (command.kind === "tool") {
    return { type: "draft", draft: `${command.names[0]} `, note: "" };
  }
  if (command.id === "help") return { type: "draft", draft: "/", note: "" };
  return runCommand(command.id, prefs, "");
}

export function runCommand(id: string, prefs: ChatPrefs, arg: string): CommandResult {
  const command = commandById(id);
  if (!command) return { type: "block", note: "unknown command" };
  if (command.kind === "tool") {
    if (arg.trim()) {
      return { type: "send", text: arg.trim(), note: "sent as text — this route has no force-tool header" };
    }
    if (id === "websearch" || id === "digisearch" || id === "digivault") return toggleTool(id, prefs);
    return { type: "note", note: "" };
  }
  if (id === "view" || id === "thinking" || id === "effort" || id === "search-engine" || id === "lang") {
    if (!arg.trim()) return { type: "choices", id, note: "" };
    if (id === "lang") {
      const code = languageId(arg);
      if (!code) return { type: "choices", id, note: "" };
      return applyChoice("lang", code, prefs);
    }
    const applied = applyChoice(id, arg.trim().toLowerCase(), prefs);
    return applied.type === "note" ? { type: "choices", id, note: "" } : applied;
  }
  if (id === "settings") return { type: "pane", pane: "settings", note: "" };
  if (id === "models") return { type: "pane", pane: "models", note: "" };
  if (id === "byok") return { type: "pane", pane: "provider", note: "" };
  if (id === "mcp") return { type: "pane", pane: "mcp", note: "" };
  if (id === "tools") return { type: "pane", pane: "tools", note: "" };
  if (id === "sessions") return { type: "sessions", note: "" };
  if (id === "new" || id === "clear") return { type: "new-session", note: "" };
  if (id === "compact") return { type: "note", note: "compact is not available on this route" };
  if (id === "undo") return { type: "note", note: "one branch" };
  if (id === "redo") return { type: "redo", note: "" };
  if (id === "copy") return { type: "copy", note: "" };
  if (id === "export") return { type: "export", note: "" };
  if (id === "charts") {
    return {
      type: "note",
      note: "charts: open in web (ASCII render may slip) — see DigiChat at the chat endpoint",
    };
  }
  if (id === "help") return { type: "draft", draft: "/", note: "" };
  return { type: "note", note: command.hint };
}

export function submitDraft(draft: string, prefs: ChatPrefs): CommandResult {
  const text = draft.trim();
  if (!text.startsWith("/")) {
    if (!text) return { type: "block", note: "" };
    return { type: "send", text, note: "" };
  }
  const [token, ...rest] = text.split(/\s+/);
  const arg = rest.join(" ").trim();
  const command = token ? findCommand(token) : undefined;
  if (!command) {
    const code = token ? languageId(token) : null;
    if (code) return applyChoice("lang", code, prefs);
    return { type: "block", note: "unknown command" };
  }
  return runCommand(command.id, prefs, arg);
}

export type SettingRow = { id: string; label: string; description: string; kind: "toggle" | "choice" | "pane" };

export function settingsRows(prefs: ChatPrefs): SettingRow[] {
  return [
    { id: "websearch", label: "web search", description: onOff(prefs.webSearch, "External cites", "corpus only"), kind: "toggle" },
    { id: "digisearch", label: "digisearch", description: onOff(prefs.digisearch, "knowledge base", "disabled this session"), kind: "toggle" },
    { id: "digivault", label: "digivault", description: onOff(prefs.digivault, "vault notes", "disabled this session"), kind: "toggle" },
    { id: "view", label: "view", description: prefs.view, kind: "choice" },
    { id: "thinking", label: "thinking", description: prefs.thinking, kind: "choice" },
    { id: "lang", label: "language", description: languageLabel(prefs.language), kind: "choice" },
    { id: "effort", label: "effort", description: prefs.effort, kind: "choice" },
    { id: "search-engine", label: "search engine", description: prefs.searchEngine, kind: "choice" },
    { id: "models", label: "models", description: prefs.model || "Pick model", kind: "pane" },
    { id: "byok", label: "provider", description: prefs.provider || "API provider", kind: "pane" },
    { id: "mcp", label: "mcp", description: "MCP JSON / auth / new", kind: "pane" },
    { id: "tools", label: "tools", description: "Connected tools", kind: "pane" },
  ];
}

export function activateSetting(id: string, prefs: ChatPrefs): CommandResult {
  if (id === "websearch" || id === "digisearch" || id === "digivault") return toggleTool(id, prefs);
  return runCommand(id, prefs, "");
}

export function paneRows(pane: Pane, prefs: ChatPrefs): PaletteRow[] {
  if (pane === "settings") {
    return settingsRows(prefs).map((row) => ({
      id: row.id,
      label: row.label,
      description: row.description,
    }));
  }
  if (pane === "provider") {
    return [
      ...PROVIDERS.map((id) => ({
        id,
        label: id,
        description: prefs.provider === id ? "selected" : "API provider",
      })),
      { id: "keys", label: "key", description: "not entered — this route accepts text only" },
    ];
  }
  if (pane === "models") return [{ id: "empty", label: "No models returned.", description: "" }];
  if (pane === "mcp") {
    return [
      { id: "empty", label: "No MCP servers.", description: "" },
      { id: "new", label: "new", description: "OAuth needs a browser" },
    ];
  }
  if (pane === "tools") return [{ id: "empty", label: "No connected tools.", description: "" }];
  if (pane === "help") return allRows(prefs);
  if (pane === "more") return [{ id: "export", label: "export", description: "Export as Markdown" }];
  return [];
}

export function selectProvider(id: string, prefs: ChatPrefs): CommandResult {
  if (!(PROVIDERS as readonly string[]).includes(id)) return { type: "note", note: "" };
  return withPrefs({ ...prefs, provider: id }, `provider ${id}`);
}

export function nextIndex(current: number, delta: number, length: number): number {
  if (length <= 0) return 0;
  return (current + delta + length) % length;
}

export function commandIds(): string[] {
  return COMMANDS.map((command) => command.id);
}
