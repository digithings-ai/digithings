#!/usr/bin/env bun
// digichat-devkit CLI — configure a digichat look from the terminal or an agent.
//
// It drives the same config the web devkit and the TUI read: the devkit config
// service (default http://127.0.0.1:3006, override with DIGICHAT_DEVKIT_URL).
// Reads go through GET /api/devkit/configs; writes go through POST /api/devkit/save,
// which validates, backs up to <file>.bak and restores the preserved secrets.
//
// Pure helpers (arg parsing, key paths, mode aliases, YAML round-trip) are
// separated from the network calls so `bun test` can cover them without a server.
import { dump, load } from "js-yaml";
import { DASH } from "./read";

export const DEFAULT_URL = process.env.DIGICHAT_DEVKIT_URL ?? "http://127.0.0.1:3006";

export const HELP = [
  "digichat-devkit — configure a digichat look",
  "",
  "usage: digichat-devkit <command> [args] [--url <base>] [--json]",
  "",
  "commands",
  "  looks                                  list the looks (config files and env tenants)",
  "  get <look> [key.path]                  read a look (whole YAML) or one key",
  "  set <look> <key.path> <value>          set one key and save",
  "  mode <look> <mode>                     set chrome.mode: fullscreen | popup | embedded | sidebar",
  "  export <look>                          print the look as YAML",
  "  import <look> <file.yaml>              save a YAML file into a look (or new:<slug>.yaml)",
  "  validate <file.yaml>                   validate a YAML file against the schema",
  "",
  "flags",
  "  --url <base>   devkit config service (default DIGICHAT_DEVKIT_URL, else " + DEFAULT_URL + ")",
  "  --json         machine-readable output",
  "  --string       keep the value as a string when it looks like a number or boolean",
  "",
  "<look> matches an entry id, its file path, its file name, or its label (slug).",
].join("\n");

export type CliEntry = {
  id: string;
  kind: "file" | "env";
  path: string | null;
  label: string;
  readOnly: boolean;
  ok: boolean;
  issues: string[];
  /** Redacted file text (secrets replaced by the preserved sentinel). Null for env tenants. */
  text: string | null;
  deployment: Record<string, unknown> | null;
};

export type ConfigsResult = { ok: true; entries: CliEntry[] } | { ok: false; detail: string };

export type WriteResult = { ok: boolean; backup?: string; issues?: string[]; detail?: string };

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>;

export type Io = { out: (line: string) => void; err: (line: string) => void };

export const DEFAULT_IO: Io = {
  out: (line) => console.log(line),
  err: (line) => console.error(line),
};

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

function root(base: string): string {
  return base.replace(/\/+$/, "");
}

async function readJson(res: Response): Promise<unknown> {
  const text = await res.text();
  if (text.length === 0) return null;
  try {
    return JSON.parse(text) as unknown;
  } catch {
    return null;
  }
}

function strings(value: unknown): string[] {
  return Array.isArray(value)
    ? value.filter((item): item is string => typeof item === "string" && item.length > 0)
    : [];
}

// ---------------------------------------------------------------- config reads

export function parseEntry(raw: unknown): CliEntry | null {
  if (!isRecord(raw)) return null;
  if (typeof raw.id !== "string" || raw.id.length === 0) return null;
  if (raw.kind !== "file" && raw.kind !== "env") return null;
  if (typeof raw.label !== "string" || raw.label.length === 0) return null;
  return {
    id: raw.id,
    kind: raw.kind,
    path: typeof raw.path === "string" ? raw.path : null,
    label: raw.label,
    readOnly: raw.readOnly === true || raw.kind === "env",
    ok: raw.ok === true,
    issues: strings(raw.issues),
    text: typeof raw.redactedText === "string" && raw.redactedText.length > 0 ? raw.redactedText : null,
    deployment: isRecord(raw.deployment) ? raw.deployment : null,
  };
}

export function interpretConfigs(body: unknown): ConfigsResult {
  if (!isRecord(body) || !Array.isArray(body.entries)) return { ok: false, detail: "configs unreadable" };
  const parsed = body.entries.map(parseEntry);
  if (parsed.some((entry) => entry === null)) return { ok: false, detail: "configs unreadable" };
  return { ok: true, entries: parsed as CliEntry[] };
}

/** Match a look by id, dotted path tail, file name, base name or label. */
export function entryMatches(entry: CliEntry, selector: string): boolean {
  if (entry.id === selector || entry.label === selector) return true;
  const tail = entry.id.replace(/^(file|env):/, "");
  if (tail === selector) return true;
  const path = tail.split("#")[0];
  if (path === selector) return true;
  const base = path.split("/").pop() ?? "";
  if (base === selector) return true;
  return base.replace(/\.ya?ml$/, "") === selector;
}

export function findEntry(entries: CliEntry[], selector: string): CliEntry | null {
  return entries.find((entry) => entryMatches(entry, selector)) ?? null;
}

// ------------------------------------------------------------------- key paths

/** Dotted key -> parts. Dots inside a part (a host name) are passed in whole, not dotted. */
export function splitPath(path: string): string[] {
  return path.split(".").filter(Boolean);
}

export function pathGet(record: unknown, path: string): unknown {
  let cur: unknown = record;
  for (const key of splitPath(path)) {
    if (!isRecord(cur)) return undefined;
    cur = cur[key];
  }
  return cur;
}

/** Immutable nested set. Intermediate mappings are created; the input is not mutated. */
export function pathSet(
  record: Record<string, unknown> | null,
  parts: string[],
  value: unknown,
): Record<string, unknown> {
  if (parts.length === 0) throw new Error("empty key path");
  const out: Record<string, unknown> = record ? structuredClone(record) : {};
  let cur: Record<string, unknown> = out;
  for (let i = 0; i < parts.length - 1; i++) {
    const key = parts[i];
    if (!isRecord(cur[key])) cur[key] = {};
    cur = cur[key] as Record<string, unknown>;
  }
  cur[parts[parts.length - 1]] = value;
  return out;
}

/**
 * Where a deployment-relative key lives in the config file. A plain look wraps the
 * deployment under `deployment:`; a host-scoped look nests it under `hosts: <host>:`.
 */
export function fileKeyParts(entry: CliEntry, key: string): string[] {
  const hash = entry.id.indexOf("#");
  if (hash < 0) return ["deployment", ...splitPath(key)];
  const scope = entry.id.slice(hash + 1).split("/").filter(Boolean);
  return [...scope, ...splitPath(key)];
}

function yamlScalar(value: unknown): string {
  return dump(value, { lineWidth: 120 }).replace(/\n+$/, "");
}

function indentOf(line: string): number {
  return line.length - line.trimStart().length;
}

function isBlank(line: string): boolean {
  return /^\s*$/.test(line);
}

function isComment(line: string): boolean {
  return /^\s*#/.test(line);
}

type Frame = { indent: number; key: string };

/** Index of the line whose mapping path equals `parts`, or -1. */
export function findKeyLine(lines: string[], parts: string[]): number {
  const stack: Frame[] = [];
  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    if (isBlank(line) || isComment(line)) continue;
    const match = /^(\s*)([^:#\n]+?):(\s|$)/.exec(line);
    if (!match) continue;
    const indent = match[1].length;
    const key = match[2].trim();
    while (stack.length > 0 && stack[stack.length - 1].indent >= indent) stack.pop();
    stack.push({ indent, key });
    if (stack.length === parts.length && stack.every((frame, index) => frame.key === parts[index])) return i;
  }
  return -1;
}

function endOfBlock(lines: string[], index: number): number {
  const base = indentOf(lines[index]);
  let cursor = index + 1;
  while (cursor < lines.length && (isBlank(lines[cursor]) || indentOf(lines[cursor]) > base)) cursor++;
  return cursor;
}

/** Replace only the value on a mapping line, keeping its key, spacing and inline comment. */
export function replaceScalar(line: string, value: unknown): string {
  const match = /^(\s*[^#\n]*?:)([ \t]*)(.*)$/.exec(line);
  if (!match) return line;
  const [, head, , rest] = match;
  const commentAt = rest.indexOf(" #");
  const comment = commentAt >= 0 ? rest.slice(commentAt).trim() : "";
  return `${head} ${yamlScalar(value)}${comment ? ` ${comment}` : ""}`;
}

/** Surgical edit: keep every comment, blank line and key order; touch one value. */
export function applySetPath(text: string, parts: string[], value: unknown): string {
  if (parts.length === 0) throw new Error("empty key path");
  const lines = text.replace(/\n$/, "").split("\n");
  const existing = findKeyLine(lines, parts);
  if (existing >= 0) {
    lines[existing] = replaceScalar(lines[existing], value);
    return `${lines.join("\n")}\n`;
  }
  const parent = parts.slice(0, -1);
  const leaf = parts[parts.length - 1];
  if (parent.length === 0) {
    lines.push(`${leaf}: ${yamlScalar(value)}`);
    return `${lines.join("\n")}\n`;
  }
  const parentLine = findKeyLine(lines, parent);
  if (parentLine >= 0 && !isBlank(lines[parentLine]) && !lines[parentLine].trimEnd().endsWith(":")) {
    return applySetPath(text, parent, { [leaf]: value });
  }
  if (parentLine < 0) {
    const parsed = load(text);
    if (!isRecord(parsed)) throw new Error("config is not a mapping");
    return dump(pathSet(parsed, parts, value), { lineWidth: 120, noRefs: true });
  }
  lines.splice(endOfBlock(lines, parentLine), 0, `${" ".repeat(indentOf(lines[parentLine]) + 2)}${leaf}: ${yamlScalar(value)}`);
  return `${lines.join("\n")}\n`;
}

/** Dotted convenience wrapper. */
export function applySet(text: string, path: string, value: unknown): string {
  return applySetPath(text, splitPath(path), value);
}

// ------------------------------------------------------------------- value typing

export const MODE_ALIASES: Record<string, string> = {
  fullscreen: "app",
  app: "app",
  popup: "modal",
  modal: "modal",
  embedded: "embed",
  embed: "embed",
  inline: "embed",
  sidebar: "sidebar",
};

export function parseMode(word: string): string | null {
  return MODE_ALIASES[word.trim().toLowerCase()] ?? null;
}

export function coerce(raw: string): unknown {
  const word = raw.trim();
  if (word === "true") return true;
  if (word === "false") return false;
  if (word === "null") return null;
  if (/^-?\d+(\.\d+)?$/.test(word)) return Number(word);
  if ((word.startsWith("[") && word.endsWith("]")) || (word.startsWith("{") && word.endsWith("}"))) {
    try {
      return JSON.parse(word) as unknown;
    } catch {
      return raw;
    }
  }
  return raw;
}

export function formatValue(value: unknown): string {
  if (value === undefined) return DASH;
  if (typeof value === "string") return value;
  if (value === null || typeof value === "number" || typeof value === "boolean") return JSON.stringify(value);
  return JSON.stringify(value, null, 2);
}

export function looksTable(entries: CliEntry[]): string {
  const width = entries.reduce((max, entry) => Math.max(max, entry.label.length), 8);
  return entries
    .map((entry) => {
      const state = entry.readOnly ? "read-only" : entry.ok ? "ok" : `invalid: ${entry.issues.join("; ") || "unknown"}`;
      return `${entry.label.padEnd(width, " ")}  ${entry.kind.padEnd(4, " ")}  ${state}  ${entry.id}`;
    })
    .join("\n");
}

// -------------------------------------------------------------------- arguments

export type ParsedArgs = { command: string; args: string[]; flags: Record<string, string | boolean> };

export function parseArgs(argv: string[]): ParsedArgs {
  const positionals: string[] = [];
  const flags: Record<string, string | boolean> = {};
  for (let i = 0; i < argv.length; i++) {
    const token = argv[i];
    if (token === "--") {
      positionals.push(...argv.slice(i + 1));
      break;
    }
    if (token.startsWith("--")) {
      const body = token.slice(2);
      const eq = body.indexOf("=");
      if (eq >= 0) {
        flags[body.slice(0, eq)] = body.slice(eq + 1);
        continue;
      }
      const next = argv[i + 1];
      if (next !== undefined && !next.startsWith("--")) {
        flags[body] = next;
        i++;
      } else {
        flags[body] = true;
      }
      continue;
    }
    positionals.push(token);
  }
  const [command = "help", ...args] = positionals;
  return { command, args, flags };
}

// --------------------------------------------------------------------- network

export async function fetchConfigs(base: string, fetchImpl: FetchLike = fetch): Promise<ConfigsResult> {
  const url = root(base);
  try {
    const res = await fetchImpl(`${url}/api/devkit/configs`, { headers: { accept: "application/json" } });
    if (res.status !== 200) return { ok: false, detail: `configs ${res.status}` };
    const body = await readJson(res);
    if (body === null) return { ok: false, detail: "configs unreadable" };
    return interpretConfigs(body);
  } catch {
    return { ok: false, detail: `configs unreachable at ${url}` };
  }
}

export async function saveConfig(
  base: string,
  id: string,
  text: string,
  fetchImpl: FetchLike = fetch,
): Promise<WriteResult> {
  const url = root(base);
  try {
    const res = await fetchImpl(`${url}/api/devkit/save`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ id, text }),
    });
    const body = await readJson(res);
    if (isRecord(body) && body.ok === true) {
      return { ok: true, backup: typeof body.backup === "string" ? body.backup : undefined };
    }
    const issues = isRecord(body) ? strings(body.issues) : [];
    return { ok: false, issues, detail: `save ${res.status}` };
  } catch {
    return { ok: false, detail: `save unreachable at ${url}` };
  }
}

export async function validateText(base: string, text: string, fetchImpl: FetchLike = fetch): Promise<WriteResult> {
  const url = root(base);
  try {
    const res = await fetchImpl(`${url}/api/devkit/validate`, {
      method: "POST",
      headers: { "content-type": "application/json", accept: "application/json" },
      body: JSON.stringify({ text }),
    });
    const body = await readJson(res);
    if (isRecord(body) && body.ok === true) return { ok: true };
    const issues = isRecord(body) ? strings(body.issues) : [];
    return { ok: false, issues, detail: `validate ${res.status}` };
  } catch {
    return { ok: false, detail: `validate unreachable at ${url}` };
  }
}

// ------------------------------------------------------------------------ main

function fail(io: Io, detail: string, code = 1): number {
  io.err(detail);
  return code;
}

async function loadOrReport(base: string, fetchImpl: FetchLike, io: Io): Promise<CliEntry[] | number> {
  const read = await fetchConfigs(base, fetchImpl);
  if (!read.ok) return fail(io, read.detail);
  return read.entries;
}

async function resolveWritable(
  base: string,
  selector: string,
  fetchImpl: FetchLike,
  io: Io,
): Promise<CliEntry | number> {
  const entries = await loadOrReport(base, fetchImpl, io);
  if (typeof entries === "number") return entries;
  const entry = findEntry(entries, selector);
  if (!entry) return fail(io, `no look matches '${selector}'`);
  if (entry.kind !== "file" || entry.readOnly) return fail(io, `look '${entry.label}' is read-only (environment tenant)`);
  if (!entry.text) return fail(io, `look '${entry.label}' has no editable text`);
  return entry;
}

export async function main(argv: string[], io: Io = DEFAULT_IO, fetchImpl: FetchLike = fetch): Promise<number> {
  const { command, args, flags } = parseArgs(argv);
  const json = flags.json === true;
  const base = typeof flags.url === "string" ? flags.url : DEFAULT_URL;
  const emitJson = (value: unknown) => io.out(JSON.stringify(value, null, 2));

  if (command === "help" || command === "-h" || flags.help === true) {
    io.out(HELP);
    return 0;
  }

  if (command === "looks" || command === "list") {
    const entries = await loadOrReport(base, fetchImpl, io);
    if (typeof entries === "number") return entries;
    if (json) emitJson(entries);
    else io.out(entries.length === 0 ? "no looks" : looksTable(entries));
    return 0;
  }

  if (command === "get" || command === "export") {
    const [selector, key] = args;
    if (!selector) return fail(io, `usage: ${command} <look>${command === "get" ? " [key.path]" : ""}`, 2);
    const entries = await loadOrReport(base, fetchImpl, io);
    if (typeof entries === "number") return entries;
    const entry = findEntry(entries, selector);
    if (!entry) return fail(io, `no look matches '${selector}'`);
    if (command === "export") {
      io.out(entry.text ?? dump(entry.deployment ?? {}, { lineWidth: 120, noRefs: true }));
      return 0;
    }
    if (!key) {
      if (json) emitJson(entry.deployment ?? {});
      else io.out(entry.text ?? dump(entry.deployment ?? {}, { lineWidth: 120, noRefs: true }));
      return 0;
    }
    const value = pathGet(entry.deployment, key);
    io.out(json ? JSON.stringify(value ?? null, null, 2) : formatValue(value));
    return 0;
  }

  if (command === "set" || command === "mode") {
    const [selector, ...rest] = args;
    if (!selector) return fail(io, `usage: ${command} <look> ${command === "mode" ? "<mode>" : "<key.path> <value>"}`, 2);
    let key: string;
    let value: unknown;
    if (command === "mode") {
      const [word] = rest;
      if (!word) return fail(io, "usage: mode <look> <fullscreen|popup|embedded|sidebar>", 2);
      const mapped = parseMode(word);
      if (!mapped) return fail(io, `unknown mode '${word}' (fullscreen|popup|embedded|sidebar)`, 2);
      key = "chrome.mode";
      value = mapped;
    } else {
      const [keyPath, rawValue] = rest;
      if (!keyPath || rawValue === undefined) return fail(io, "usage: set <look> <key.path> <value>", 2);
      key = keyPath;
      value = flags.string === true ? rawValue : coerce(rawValue);
    }
    const entry = await resolveWritable(base, selector, fetchImpl, io);
    if (typeof entry === "number") return entry;
    let next: string;
    try {
      next = applySetPath(entry.text as string, fileKeyParts(entry, key), value);
    } catch (error) {
      return fail(io, `cannot set ${key}: ${error instanceof Error ? error.message : String(error)}`);
    }
    const saved = await saveConfig(base, entry.id, next, fetchImpl);
    if (!saved.ok) return fail(io, saved.issues?.join("; ") || saved.detail || "save failed");
    if (json) emitJson({ ok: true, id: entry.id, key, value, backup: saved.backup ?? null });
    else io.out(`set ${entry.label} ${key} = ${formatValue(value)}${saved.backup ? `  (backup ${saved.backup})` : ""}`);
    return 0;
  }

  if (command === "import") {
    const [selector, file] = args;
    if (!selector || !file) return fail(io, "usage: import <look> <file.yaml>", 2);
    let text: string;
    try {
      text = await Bun.file(file).text();
    } catch {
      return fail(io, `cannot read ${file}`);
    }
    const entries = await loadOrReport(base, fetchImpl, io);
    if (typeof entries === "number") return entries;
    let id = selector;
    const entry = findEntry(entries, selector);
    if (entry) {
      if (entry.kind !== "file" || entry.readOnly) return fail(io, `look '${entry.label}' is read-only (environment tenant)`);
      id = entry.id;
    } else if (!selector.startsWith("new:")) {
      id = `new:${selector.replace(/\.ya?ml$/, "")}.yaml`;
    }
    const saved = await saveConfig(base, id, text, fetchImpl);
    if (!saved.ok) return fail(io, saved.issues?.join("; ") || saved.detail || "save failed");
    if (json) emitJson({ ok: true, id, backup: saved.backup ?? null });
    else io.out(`imported ${file} -> ${id}${saved.backup ? `  (backup ${saved.backup})` : ""}`);
    return 0;
  }

  if (command === "validate") {
    const [file] = args;
    if (!file) return fail(io, "usage: validate <file.yaml>", 2);
    let text: string;
    try {
      text = await Bun.file(file).text();
    } catch {
      return fail(io, `cannot read ${file}`);
    }
    const result = await validateText(base, text, fetchImpl);
    if (result.ok) {
      if (json) emitJson({ ok: true });
      else io.out("ok");
      return 0;
    }
    return fail(io, result.issues?.join("\n") || result.detail || "invalid");
  }

  io.err(`unknown command '${command}'`);
  io.out(HELP);
  return 2;
}

if (import.meta.main) {
  process.exit(await main(process.argv.slice(2)));
}
