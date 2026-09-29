/**
 * devkit draft model + line-based YAML text helpers (client-safe).
 *
 * No yaml lib in the client bundle (parse/validate/dump stay server-side),
 * so form edits rewrite the draft text line-wise and the draft is
 * revalidated through `POST /api/devkit/validate` (debounced by the caller).
 * Raw YAML and forms can never diverge: both operate on `draft.text`.
 *
 * Helpers never parse values — they match `key:` lines at the expected
 * indentation inside the entry's scope (`["deployment"]` for top-level
 * entries, `["hosts", hostKey]` for hosts sub-entries, which share one file).
 * An edit that would be unsafe (key owns nested block content, anchor
 * structure conflicts) returns `applied: false` and leaves the text
 * untouched — the UI then falls back to raw YAML.
 */
import type { DigichatDeployment } from "@/lib/deploy-config/schema";

/** Path from the document root to the entry's deployment map. */
export type DraftScope = string[];

export type EntryDraft = {
  /** Null for unsaved new-file drafts (no entry until first save). */
  entryId: string | null;
  scope: DraftScope;
  /** Last-saved redacted text (`""` for new files). */
  savedText: string;
  /** Current draft text (raw YAML or form-rewritten). */
  text: string;
  /**
   * Last-valid parsed deployment (secret-stripped) — seeds the preview.
   * Stays put while the draft is invalid; the caller refreshes it from the
   * validate response via `withValidation`.
   */
  parsed: DigichatDeployment | null;
  /** Current validation issues for `text` (empty when valid). */
  issues: string[];
};

export function createDraft(args: {
  entryId: string | null;
  scope: DraftScope;
  savedText: string;
  parsed: DigichatDeployment | null;
}): EntryDraft {
  return {
    entryId: args.entryId,
    scope: [...args.scope],
    savedText: args.savedText,
    text: args.savedText,
    parsed: args.parsed,
    issues: [],
  };
}

/** Dirty is a plain string compare against the last-saved text. */
export function isDirty(draft: EntryDraft): boolean {
  return draft.text !== draft.savedText;
}

export function withText(draft: EntryDraft, text: string): EntryDraft {
  return { ...draft, text };
}

/**
 * Fold a validate-response into the draft: issues always refresh; `parsed`
 * only advances when the server returns a deployment (valid draft), so an
 * invalid draft keeps previewing its last-valid state.
 */
export function withValidation(
  draft: EntryDraft,
  result: { issues: string[]; deployment?: DigichatDeployment | null },
): EntryDraft {
  return {
    ...draft,
    issues: result.issues,
    parsed: result.deployment ?? draft.parsed,
  };
}

/** Template text for new-file drafts (single source; savedText seeds from it). */
export const NEW_FILE_TEMPLATE =
  "version: 1\ndeployment:\n  slug: new-deployment\n  backend:\n    type: digigraph\n";

/**
 * New-file drafts start from the template with no entry. savedText seeds
 * from the template so a pristine new-file draft is clean (m1: previously
 * savedText was "" which made every fresh draft dirty-by-construction and
 * triggered phantom discard-confirms). Whether the file exists on disk is
 * tracked by entryId (null until the first save), not by dirtiness.
 */
export function createNewFileDraft(): EntryDraft {
  return {
    entryId: null,
    scope: ["deployment"],
    savedText: NEW_FILE_TEMPLATE,
    text: NEW_FILE_TEMPLATE,
    parsed: null,
    issues: [],
  };
}

/** Slug rule shared by the new-file flow (mirrors the plan contract). */
export function isValidSlug(slug: string): boolean {
  return /^[a-z0-9-]+$/.test(slug);
}

export type TextEdit = {
  /** Resulting full text (byte-identical to input when `applied` is false). */
  text: string;
  applied: boolean;
};

function indentOf(line: string): number {
  return /^(\s*)/.exec(line)?.[1].length ?? 0;
}

function isBlankOrComment(line: string): boolean {
  const t = line.trim();
  return t === "" || t.startsWith("#");
}

/** `key:` header line at any indent; captures indent, key, and the rest. */
function matchKeyLine(line: string): {
  indent: number;
  key: string;
  rest: string;
} | null {
  const m = /^(\s*)([^:#\s][^:]*?)\s*:(.*)$/.exec(line);
  if (!m) return null;
  // A dash-led line (`- id: x`) is a sequence item, never a map key.
  if (/^\s*-(\s|$)/.test(line)) return null;
  return { indent: m[1].length, key: m[2].trim(), rest: m[3] };
}

type MapRange = { header: number; end: number; indent: number };

/**
 * Locate the line range of the map at `scope` (scope[0] is top-level).
 * `end` is the first line past the map (exclusive): the first non-blank,
 * non-comment line at indent <= the header's, or EOF.
 */
function locateScope(lines: string[], scope: DraftScope): MapRange | null {
  let start = 0;
  let end = lines.length;
  let indent = -1;
  for (const segment of scope) {
    let header = -1;
    for (let i = start; i < end; i++) {
      if (isBlankOrComment(lines[i])) continue;
      const k = matchKeyLine(lines[i]);
      if (k && k.key === segment && k.indent > indent) {
        header = i;
        indent = k.indent;
        break;
      }
    }
    if (header === -1) return null;
    let close = end;
    for (let i = header + 1; i < end; i++) {
      if (isBlankOrComment(lines[i])) continue;
      if (indentOf(lines[i]) <= indent) {
        close = i;
        break;
      }
    }
    start = header;
    end = close;
  }
  return { header: start, end, indent };
}

/**
 * Within an already-located parent map, find a direct child `key` line.
 * The child indent is detected from the first child seen.
 */
function locateChild(
  lines: string[],
  parent: MapRange,
  key: string,
): { index: number; indent: number } | null {
  let childIndent: number | null = null;
  for (let i = parent.header + 1; i < parent.end; i++) {
    if (isBlankOrComment(lines[i])) continue;
    const k = matchKeyLine(lines[i]);
    if (!k || k.indent <= parent.indent) continue;
    if (childIndent === null) {
      childIndent = k.indent;
    }
    if (k.indent !== childIndent) continue;
    if (k.key === key) return { index: i, indent: k.indent };
  }
  return null;
}

function childIndentFor(lines: string[], parent: MapRange): number {
  for (let i = parent.header + 1; i < parent.end; i++) {
    if (isBlankOrComment(lines[i])) continue;
    const k = matchKeyLine(lines[i]);
    if (k && k.indent > parent.indent) return k.indent;
  }
  return parent.indent + 2;
}

/** True when the key line owns nested block content (unsafe to overwrite). */
function hasBlockContent(lines: string[], keyIndex: number, keyIndent: number): boolean {
  for (let i = keyIndex + 1; i < lines.length; i++) {
    if (isBlankOrComment(lines[i])) continue;
    return indentOf(lines[i]) > keyIndent;
  }
  return false;
}

/**
 * Ensure the map at `keyPath` (relative to scope) exists, creating missing
 * tail segments as empty maps. Returns the edited lines plus the target map
 * range, or null when the existing structure conflicts (scalar in the way).
 */
function ensureMap(
  lines: string[],
  scope: MapRange,
  keyPath: string[],
): { lines: string[]; map: MapRange } | null {
  const next = [...lines];
  let current = scope;
  for (const segment of keyPath) {
    const found = locateChild(next, current, segment);
    if (found) {
      if (hasBlockContent(next, found.index, found.indent)) {
        // Descend into the existing child map.
        let close = current.end;
        for (let i = found.index + 1; i < current.end; i++) {
          if (isBlankOrComment(next[i])) continue;
          if (indentOf(next[i]) <= found.indent) {
            close = i;
            break;
          }
        }
        current = { header: found.index, end: close, indent: found.indent };
        continue;
      }
      // Key exists as a scalar (`key: value`) where a map is needed.
      return null;
    }
    const indent = childIndentFor(next, current);
    const insertAt = current.header + 1;
    next.splice(insertAt, 0, `${" ".repeat(indent)}${segment}:`);
    // The new empty map spans to the previous end (shifted by insertion).
    current = { header: insertAt, end: current.end + 1, indent };
  }
  return { lines: next, map: current };
}

/**
 * The server redaction sentinel. Must equal `DEVKIT_SENTINEL` in
 * `lib/devkit-configs.ts` (server-only module — duplicated here so this
 * client-safe module can name it; equality is pinned by test).
 */
export const DEVKIT_SENTINEL = "__DEVKIT_PRESERVED__";

/**
 * Descend `keyPath` (string segments only) through EXISTING maps, creating
 * nothing. Returns the target map range, or null when a segment is missing
 * or a scalar/list stands in the way.
 */
function descendExisting(
  lines: string[],
  scope: MapRange,
  keyPath: string[],
): MapRange | null {
  let current = scope;
  for (const segment of keyPath) {
    const found = locateChild(lines, current, segment);
    if (!found || !hasBlockContent(lines, found.index, found.indent)) return null;
    let close = current.end;
    for (let i = found.index + 1; i < current.end; i++) {
      if (isBlankOrComment(lines[i])) continue;
      if (indentOf(lines[i]) <= found.indent) {
        close = i;
        break;
      }
    }
    current = { header: found.index, end: close, indent: found.indent };
  }
  return current;
}

/** Locate a map `keyPath` (relative to scope) without creating anything. */
function locateKey(
  lines: string[],
  scope: DraftScope,
  keyPath: string[],
): { index: number; indent: number } | null {
  const scopeRange = locateScope(lines, scope);
  if (!scopeRange || keyPath.length === 0) return null;
  const parent = descendExisting(lines, scopeRange, keyPath.slice(0, -1));
  if (!parent) return null;
  return locateChild(lines, parent, keyPath[keyPath.length - 1]);
}

/**
 * End (exclusive) of the block owned by a key line: consumes following
 * blank/comment lines and deeper-indented lines, then backs off trailing
 * separators so sibling spacing survives.
 */
function ownedBlockEnd(lines: string[], keyIndex: number, keyIndent: number): number {
  let end = keyIndex + 1;
  while (end < lines.length) {
    if (isBlankOrComment(lines[end])) {
      end++;
      continue;
    }
    if (indentOf(lines[end]) <= keyIndent) break;
    end++;
  }
  while (end - 1 > keyIndex && isBlankOrComment(lines[end - 1])) end--;
  return end;
}

/**
 * Delete the key at `keyPath` (relative to scope) with its owned block.
 * Returns `applied: false` (text untouched) when the key is already absent
 * or the structure is missing.
 */
export function deleteKey(text: string, scope: DraftScope, keyPath: string[]): TextEdit {
  if (keyPath.length === 0) return { text, applied: false };
  const lines = text.split("\n");
  const found = locateKey(lines, scope, keyPath);
  if (!found) return { text, applied: false };
  const end = ownedBlockEnd(lines, found.index, found.indent);
  const next = [...lines];
  next.splice(found.index, end - found.index);
  return { text: next.join("\n"), applied: true };
}

type ListItemRange = { dashIndex: number; end: number; indent: number };

/**
 * List items owned by the key at `keyIndex`: consecutive `- ` lines at one
 * indent, each owning its deeper-indented continuation lines. Returns null
 * when the key owns non-list block content (a nested map) — refusing is
 * safer than rewriting. An inline scalar (`key: []`, `key: value`) or a bare
 * key yields an empty array (appendable); use the `inline` flag to tell them
 * apart when replacing.
 */
function locateListItems(
  lines: string[],
  keyIndex: number,
  keyIndent: number,
): { items: ListItemRange[]; inline: boolean } | null {
  let i = keyIndex + 1;
  while (i < lines.length && isBlankOrComment(lines[i])) i++;
  if (i >= lines.length || indentOf(lines[i]) <= keyIndent) {
    // Bare `key:` or `key: []` is appendable; an inline scalar is not a list.
    const rest = lines[keyIndex].split(":").slice(1).join(":").trim();
    if (rest === "" || rest === "[]") return { items: [], inline: true };
    return null;
  }
  if (!isListItem(lines[i], indentOf(lines[i]))) return null;
  const itemIndent = indentOf(lines[i]);
  const items: ListItemRange[] = [];
  while (i < lines.length) {
    if (isBlankOrComment(lines[i])) {
      i++;
      continue;
    }
    if (isListItem(lines[i], itemIndent)) {
      const dashIndex = i;
      i++;
      while (
        i < lines.length &&
        (isBlankOrComment(lines[i]) || indentOf(lines[i]) > itemIndent)
      ) {
        i++;
      }
      // Back off trailing separators so a removal never eats blank lines.
      let end = i;
      while (end - 1 > dashIndex && isBlankOrComment(lines[end - 1])) end--;
      items.push({ dashIndex, end, indent: itemIndent });
      continue;
    }
    break;
  }
  return { items, inline: false };
}

/** Split a `- ` item line into its indent and the text after the dash. */
function splitDash(line: string): { indent: number; rest: string } | null {
  const m = /^(\s*)-\s+(.*)$/.exec(line);
  if (!m) return null;
  return { indent: m[1].length, rest: m[2] };
}

/**
 * Field line inside one list item: either inline on the dash line itself
 * (`- id: foo`) or a `field:` line at the item's content indent. Returns null
 * when the field is absent (insertable) or owns block content (refuse).
 */
function locateItemField(
  lines: string[],
  item: ListItemRange,
  field: string,
): { index: number; indent: number } | { missing: true; indent: number } | null {
  const dash = splitDash(lines[item.dashIndex]);
  if (!dash) return null;
  const inline = matchKeyLine(`${" ".repeat(dash.indent + 2)}${dash.rest}`);
  if (inline && inline.key === field) {
    // The dash-line field is a leaf — deeper lines belong to the item map,
    // not to this field — unless it opens a block scalar (`- id: |`).
    if (/^[|>]/.test(inline.rest.trim())) {
      if (hasBlockContent(lines, item.dashIndex, dash.indent + 2)) return null;
    }
    return { index: item.dashIndex, indent: dash.indent };
  }
  // Content indent: first content line's indent (dash line excluded).
  let contentIndent: number | null = null;
  for (let i = item.dashIndex + 1; i < item.end; i++) {
    if (isBlankOrComment(lines[i])) continue;
    contentIndent = indentOf(lines[i]);
    break;
  }
  if (contentIndent === null) {
    // Bare `- ` item with no content: field is missing, insert at +2.
    return { missing: true, indent: item.indent + 2 };
  }
  for (let i = item.dashIndex + 1; i < item.end; i++) {
    if (isBlankOrComment(lines[i])) continue;
    const k = matchKeyLine(lines[i]);
    if (!k || k.indent !== contentIndent) continue;
    if (k.key !== field) continue;
    if (hasBlockContent(lines, i, k.indent)) return null;
    return { index: i, indent: k.indent };
  }
  return { missing: true, indent: contentIndent };
}

/** Render one list-of-maps item: first pair on the dash line, rest below. */
function renderListItem(item: Record<string, string | boolean>, indent: number): string[] {
  const pad = " ".repeat(indent);
  const childPad = " ".repeat(indent + 2);
  const pairs = Object.entries(item);
  if (pairs.length === 0) return [`${pad}-`];
  const [first, ...rest] = pairs;
  return [
    `${pad}- ${first[0]}: ${renderScalar(first[1])}`,
    ...rest.map(([k, v]) => `${childPad}${k}: ${renderScalar(v)}`),
  ];
}

/**
 * Set one scalar field of the `index`-th item of the list at `listKeyPath`
 * (relative to scope). Refuses when the list, item, or field structure is
 * missing or the field owns block content.
 */
export function setListItemScalar(
  text: string,
  scope: DraftScope,
  listKeyPath: string[],
  index: number,
  field: string,
  value: string | number | boolean,
): TextEdit {
  if (listKeyPath.length === 0 || index < 0 || field === "") {
    return { text, applied: false };
  }
  const lines = text.split("\n");
  const key = locateKey(lines, scope, listKeyPath);
  if (!key) return { text, applied: false };
  const located = locateListItems(lines, key.index, key.indent);
  if (!located || index >= located.items.length) return { text, applied: false };
  const item = located.items[index];
  const found = locateItemField(lines, item, field);
  if (!found || "missing" in found) {
    if (!found) return { text, applied: false };
    const next = [...lines];
    next.splice(
      item.dashIndex + 1,
      0,
      `${" ".repeat(found.indent)}${field}: ${renderScalar(value)}`,
    );
    return { text: next.join("\n"), applied: true };
  }
  const next = [...lines];
  if (found.index === item.dashIndex) {
    const dash = splitDash(lines[found.index]);
    if (!dash) return { text, applied: false };
    next[found.index] =
      `${" ".repeat(dash.indent)}- ${field}: ${renderScalar(value)}`;
  } else {
    next[found.index] = `${" ".repeat(found.indent)}${field}: ${renderScalar(value)}`;
  }
  return { text: next.join("\n"), applied: true };
}

/**
 * Append one map item to the list at `listKeyPath`, creating the key (and
 * missing intermediate maps) when absent. Converts an inline `key: []` to a
 * block list; refuses when the key owns a scalar or a nested map.
 */
export function appendListItem(
  text: string,
  scope: DraftScope,
  listKeyPath: string[],
  item: Record<string, string | boolean>,
): TextEdit {
  if (listKeyPath.length === 0) return { text, applied: false };
  const lines = text.split("\n");
  const scopeRange = locateScope(lines, scope);
  if (!scopeRange) return { text, applied: false };
  const ensured = ensureMap(lines, scopeRange, listKeyPath.slice(0, -1));
  if (!ensured) return { text, applied: false };
  const leaf = listKeyPath[listKeyPath.length - 1];
  const found = locateChild(ensured.lines, ensured.map, leaf);
  const next = [...ensured.lines];
  if (!found) {
    const indent = childIndentFor(ensured.lines, ensured.map);
    next.splice(
      ensured.map.header + 1,
      0,
      `${" ".repeat(indent)}${leaf}:`,
      ...renderListItem(item, indent + 2),
    );
    return { text: next.join("\n"), applied: true };
  }
  const located = locateListItems(next, found.index, found.indent);
  if (!located) return { text, applied: false };
  if (located.inline) {
    // `key: []` or bare `key:` — replace the header line with a block list.
    next.splice(
      found.index,
      1,
      `${" ".repeat(found.indent)}${leaf}:`,
      ...renderListItem(item, found.indent + 2),
    );
    return { text: next.join("\n"), applied: true };
  }
  const last = located.items[located.items.length - 1];
  const at = last ? last.end : found.index + 1;
  const indent = last ? last.indent : found.indent + 2;
  next.splice(at, 0, ...renderListItem(item, indent));
  return { text: next.join("\n"), applied: true };
}

/**
 * Remove the `index`-th item of the list at `listKeyPath`. Removing the last
 * item renders `key: []` (a bare key would parse as null and fail schema).
 */
export function removeListItem(
  text: string,
  scope: DraftScope,
  listKeyPath: string[],
  index: number,
): TextEdit {
  if (listKeyPath.length === 0 || index < 0) return { text, applied: false };
  const lines = text.split("\n");
  const key = locateKey(lines, scope, listKeyPath);
  if (!key) return { text, applied: false };
  const located = locateListItems(lines, key.index, key.indent);
  if (!located || index >= located.items.length) return { text, applied: false };
  const next = [...lines];
  if (located.items.length === 1) {
    const end = located.items[0].end;
    next.splice(key.index, end - key.index, `${" ".repeat(key.indent)}${listKeyPath[listKeyPath.length - 1]}: []`);
    return { text: next.join("\n"), applied: true };
  }
  const item = located.items[index];
  next.splice(item.dashIndex, item.end - item.dashIndex);
  return { text: next.join("\n"), applied: true };
}

export type SecretState = "absent" | "sentinel" | "value";

/** Strip one layer of matching single/double quotes for sentinel compare. */
function unquoteScalar(rest: string): string {
  if (
    rest.length >= 2 &&
    ((rest.startsWith('"') && rest.endsWith('"')) ||
      (rest.startsWith("'") && rest.endsWith("'")))
  ) {
    return rest.slice(1, -1);
  }
  return rest;
}

/**
 * Classify a secret scalar at `keyPath` without ever surfacing its value:
 * `absent` (no key), `sentinel` (still the redaction placeholder — safe to
 * keep, restores from disk on save), or `value` (operator content or a
 * replacement — shown masked only). Block-scalar headers count as `value`.
 */
export function secretState(
  text: string,
  scope: DraftScope,
  keyPath: string[],
): SecretState {
  if (keyPath.length === 0) return "absent";
  const lines = text.split("\n");
  const found = locateKey(lines, scope, keyPath);
  if (!found) return "absent";
  const rest = lines[found.index].split(":").slice(1).join(":").trim();
  if (unquoteScalar(rest) === DEVKIT_SENTINEL) return "sentinel";
  return "value";
}

/**
 * Secret state for a scalar field of one list item (MCP server `token`).
 * Same contract as `secretState`; refuses structure problems as `value`
 * (masked — never displayed) rather than crashing the row.
 */
export function secretStateInList(
  text: string,
  scope: DraftScope,
  listKeyPath: string[],
  index: number,
  field: string,
): SecretState {
  if (listKeyPath.length === 0 || index < 0 || field === "") return "absent";
  const lines = text.split("\n");
  const key = locateKey(lines, scope, listKeyPath);
  if (!key) return "absent";
  const located = locateListItems(lines, key.index, key.indent);
  if (!located || index >= located.items.length) return "absent";
  const found = locateItemField(lines, located.items[index], field);
  if (!found || "missing" in found) return "absent";
  const line = lines[found.index];
  const rest =
    found.index === located.items[index].dashIndex
      ? (splitDash(line)?.rest.split(":").slice(1).join(":").trim() ?? "")
      : line.split(":").slice(1).join(":").trim();
  if (unquoteScalar(rest) === DEVKIT_SENTINEL) return "sentinel";
  return "value";
}

/**
 * Delete one scalar field of the `index`-th list item. A deeper field line
 * splices out directly; a dash-inline field promotes the first content line
 * onto the dash (`- token: x` + `url: y` becomes `- url: y`). Refuses when
 * the field is missing, owns block content, or is a lone dash pair with
 * nothing to promote.
 */
export function deleteListItemField(
  text: string,
  scope: DraftScope,
  listKeyPath: string[],
  index: number,
  field: string,
): TextEdit {
  if (listKeyPath.length === 0 || index < 0 || field === "") {
    return { text, applied: false };
  }
  const lines = text.split("\n");
  const key = locateKey(lines, scope, listKeyPath);
  if (!key) return { text, applied: false };
  const located = locateListItems(lines, key.index, key.indent);
  if (!located || index >= located.items.length) return { text, applied: false };
  const item = located.items[index];
  const found = locateItemField(lines, item, field);
  if (!found || "missing" in found) return { text, applied: false };
  const next = [...lines];
  if (found.index !== item.dashIndex) {
    next.splice(found.index, 1);
    return { text: next.join("\n"), applied: true };
  }
  let content = -1;
  for (let i = item.dashIndex + 1; i < item.end; i++) {
    if (isBlankOrComment(lines[i])) continue;
    content = i;
    break;
  }
  if (content === -1) return { text, applied: false };
  next.splice(item.dashIndex, 1, `${" ".repeat(item.indent)}- ${lines[content].trim()}`);
  next.splice(content, 1);
  return { text: next.join("\n"), applied: true };
}

/**
 * Chain text edits left to right on one snapshot: stops at the first
 * refusal and returns it (text untouched by the whole chain), otherwise the
 * final text with `applied: true`. Lets one form commit span several ops
 * (e.g. backend type switch: delete variant keys, then set the new ones).
 */
export function applyAll(text: string, runs: Array<(t: string) => TextEdit>): TextEdit {
  let current = text;
  for (const run of runs) {
    const edit = run(current);
    if (!edit.applied) return { text, applied: false };
    current = edit.text;
  }
  return runs.length > 0 ? { text: current, applied: true } : { text, applied: false };
}
export function formatYamlScalar(value: string): string {
  if (value === "") return `""`;
  const lower = value.toLowerCase();
  if (["true", "false", "yes", "no", "on", "off", "null", "~"].includes(lower)) {
    return `"${value}"`;
  }
  if (/^-?\d+(\.\d+)?$/.test(value)) return `"${value}"`;
  if (/^[A-Za-z0-9][A-Za-z0-9 _./@+-]*$/.test(value)) return value;
  return `"${value.replace(/\\/g, "\\\\").replace(/"/g, '\\"')}"`;
}

function renderScalar(value: string | number | boolean): string {
  if (typeof value === "string") return formatYamlScalar(value);
  return String(value);
}

/**
 * Set a scalar `keyPath` (relative to scope) to `value`. Creates the key
 * (and missing intermediate maps) when absent. Refuses when the key already
 * owns block content — replacing that would destroy data.
 */
export function setScalar(
  text: string,
  scope: DraftScope,
  keyPath: string[],
  value: string | number | boolean,
): TextEdit {
  if (keyPath.length === 0) return { text, applied: false };
  const lines = text.split("\n");
  const scopeRange = locateScope(lines, scope);
  if (!scopeRange) return { text, applied: false };
  const ensured = ensureMap(lines, scopeRange, keyPath.slice(0, -1));
  if (!ensured) return { text, applied: false };
  const key = keyPath[keyPath.length - 1];
  const found = locateChild(ensured.lines, ensured.map, key);
  const rendered = renderScalar(value);
  if (found) {
    if (hasBlockContent(ensured.lines, found.index, found.indent)) {
      return { text, applied: false };
    }
    const next = [...ensured.lines];
    next[found.index] = `${" ".repeat(found.indent)}${key}: ${rendered}`;
    return { text: next.join("\n"), applied: true };
  }
  const indent = childIndentFor(ensured.lines, ensured.map);
  const next = [...ensured.lines];
  next.splice(ensured.map.header + 1, 0, `${" ".repeat(indent)}${key}: ${rendered}`);
  return { text: next.join("\n"), applied: true };
}

/** Boolean specialization of `setScalar` (renders `true` / `false`). */
export function setBoolean(
  text: string,
  scope: DraftScope,
  keyPath: string[],
  value: boolean,
): TextEdit {
  if (typeof value !== "boolean") return { text, applied: false };
  return setScalar(text, scope, keyPath, value);
}

/**
 * Set the welcome title. The schema surfaces a scalar `welcome:` string as
 * the title, but the text layer cannot descend into a scalar — so when the
 * direct nested set refuses, replace the scalar with a title map
 * (delete + set, all-or-nothing via `applyAll`).
 */
export function setWelcomeTitle(text: string, scope: DraftScope, title: string): TextEdit {
  const direct = setScalar(text, scope, ["chrome", "welcome", "title"], title);
  if (direct.applied) return direct;
  return applyAll(text, [
    (t) => deleteKey(t, scope, ["chrome", "welcome"]),
    (t) => setScalar(t, scope, ["chrome", "welcome", "title"], title),
  ]);
}

function isListItem(line: string, indent: number): boolean {
  return indentOf(line) === indent && /^\s*-\s/.test(line);
}

/**
 * End (exclusive) of the block owned by a key line: consecutive list items
 * or an inline scalar (just the line itself). Returns -1 when the key owns
 * non-list block content (a nested map) — refusing is safer than rewriting.
 */
function listBlockEnd(lines: string[], keyIndex: number, keyIndent: number): number {
  let i = keyIndex + 1;
  while (i < lines.length && isBlankOrComment(lines[i])) i++;
  if (i >= lines.length || indentOf(lines[i]) <= keyIndent) {
    // Inline scalar (`key: value`, `key: []`, or bare `key:`) — just the line.
    return keyIndex + 1;
  }
  if (!isListItem(lines[i], indentOf(lines[i]))) return -1;
  const itemIndent = indentOf(lines[i]);
  let j = i;
  while (j < lines.length) {
    if (isBlankOrComment(lines[j])) {
      j++;
      continue;
    }
    // The owned region ends at the first line back at (or above) the key.
    if (indentOf(lines[j]) <= keyIndent) break;
    // A dash at the item indent continues the list; anything else nested
    // inside (block-scalar continuations, nested maps) is content this
    // line-based rewrite cannot safely preserve — refuse outright.
    if (!isListItem(lines[j], itemIndent)) return -1;
    j++;
  }
  return j;
}

/**
 * Set a string-list `keyPath` (relative to scope) to `values`, rendered as
 * a block sequence. An empty list renders inline (`key: []`). Existing item
 * lines are replaced; non-list block content under the key refuses.
 */
export function setStringList(
  text: string,
  scope: DraftScope,
  keyPath: string[],
  values: string[],
): TextEdit {
  if (keyPath.length === 0) return { text, applied: false };
  const lines = text.split("\n");
  const scopeRange = locateScope(lines, scope);
  if (!scopeRange) return { text, applied: false };
  const ensured = ensureMap(lines, scopeRange, keyPath.slice(0, -1));
  if (!ensured) return { text, applied: false };
  const key = keyPath[keyPath.length - 1];
  const found = locateChild(ensured.lines, ensured.map, key);
  const indent = found ? found.indent : childIndentFor(ensured.lines, ensured.map);
  const pad = " ".repeat(indent);

  if (values.length === 0) {
    const line = `${pad}${key}: []`;
    if (found) {
      const end = listBlockEnd(ensured.lines, found.index, found.indent);
      if (end === -1) return { text, applied: false };
      const next = [...ensured.lines];
      next.splice(found.index, end - found.index, line);
      return { text: next.join("\n"), applied: true };
    }
    const next = [...ensured.lines];
    next.splice(ensured.map.header + 1, 0, line);
    return { text: next.join("\n"), applied: true };
  }

  const itemPad = `${pad}  `;
  const itemLines = values.map((v) => `${itemPad}- ${formatYamlScalar(v)}`);
  if (found) {
    const end = listBlockEnd(ensured.lines, found.index, found.indent);
    if (end === -1) return { text, applied: false };
    const next = [...ensured.lines];
    next.splice(found.index, end - found.index, `${pad}${key}:`, ...itemLines);
    return { text: next.join("\n"), applied: true };
  }
  const next = [...ensured.lines];
  next.splice(ensured.map.header + 1, 0, `${pad}${key}:`, ...itemLines);
  return { text: next.join("\n"), applied: true };
}
