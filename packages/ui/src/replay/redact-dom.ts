/**
 * Redact a snapshot DOM before it is serialized.
 *
 * Redaction runs on text and attribute values, never on serialized HTML, so a
 * secret's replacement cannot swallow tags or the text after it. A secret that
 * the page splits across inline elements (syntax-highlighted JSON, a `code`
 * span inside a sentence) is found by redacting each inline-only block as one
 * string; only a block that held a secret loses its inline formatting.
 */

import { redactString, redactValue } from "./redact";

/** Elements whose children are phrasing content: they never start a new block. */
const INLINE = new Set([
  "A",
  "ABBR",
  "B",
  "BDI",
  "BDO",
  "BR",
  "CITE",
  "CODE",
  "DATA",
  "DFN",
  "EM",
  "I",
  "KBD",
  "MARK",
  "Q",
  "S",
  "SAMP",
  "SMALL",
  "SPAN",
  "STRONG",
  "SUB",
  "SUP",
  "TIME",
  "U",
  "VAR",
  "WBR",
]);

/** Text that is not page prose: CSS and inlined payloads. */
const SKIP = new Set(["STYLE", "SCRIPT", "SVG", "svg", "MATH", "math"]);

/**
 * Redact one block of text. JSON (a tool call's args or result) is parsed and
 * redacted by key, so `{"password": "abc"}` loses its value even when the
 * value has no token shape; anything else goes through `redactString`.
 */
export function redactBlockText(text: string): string {
  const trimmed = text.trim();
  if (
    (trimmed.startsWith("{") && trimmed.endsWith("}")) ||
    (trimmed.startsWith("[") && trimmed.endsWith("]"))
  ) {
    try {
      const parsed: unknown = JSON.parse(trimmed);
      const redacted = redactValue(parsed);
      if (JSON.stringify(redacted) !== JSON.stringify(parsed)) {
        return JSON.stringify(redacted, null, 2);
      }
      return text;
    } catch {
      /* not JSON: fall through to the text patterns */
    }
  }
  return redactString(text);
}

export function redactSnapshotDom(root: Element): void {
  redactAttributes(root);
  // Every text node first: a secret inside one node is replaced in place, so
  // links and formatting around it survive.
  const walker = root.ownerDocument.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node as Text);
  for (const node of texts) {
    if (insideSkipped(node.parentElement, root)) continue;
    const next = redactString(node.data);
    if (next !== node.data) node.data = next;
  }
  // Then each inline-only block as one string: a secret split across nodes
  // (highlighted JSON, `code` spans) is still found. Only such a block is
  // flattened to plain text.
  for (const block of inlineOnlyBlocks(root)) {
    const text = block.textContent ?? "";
    const next = redactBlockText(text);
    if (next !== text) block.textContent = next;
  }
}

function redactAttributes(root: Element): void {
  for (const el of [root, ...root.querySelectorAll("*")]) {
    if (SKIP.has(el.tagName)) continue;
    for (const attr of [...el.attributes]) {
      const value = attr.value;
      // style holds inlined url(data:…) payloads; data: URIs are the inlined assets.
      if (!value || attr.name === "style" || /^\s*data:/i.test(value)) continue;
      const next = redactString(value);
      if (next !== value) el.setAttribute(attr.name, next);
    }
  }
}

/**
 * The outermost elements whose whole subtree is inline and holds text: a `p`,
 * `pre`, `li`, a JSON view, or an inline run beside block siblings.
 */
function inlineOnlyBlocks(root: Element): Element[] {
  const candidates = [root, ...root.querySelectorAll("*")].filter((el) => {
    if (SKIP.has(el.tagName) || insideSkipped(el.parentElement, root)) return false;
    if (!el.textContent?.trim()) return false;
    for (const d of el.querySelectorAll("*")) if (!INLINE.has(d.tagName)) return false;
    return true;
  });
  return dedupeOutermost(candidates);
}

function dedupeOutermost(els: Element[]): Element[] {
  const set = new Set(els);
  return els.filter((el) => {
    for (let p = el.parentElement; p; p = p.parentElement) if (set.has(p)) return false;
    return true;
  });
}

function insideSkipped(el: Element | null, root: Element): boolean {
  for (let cursor = el; cursor; cursor = cursor.parentElement) {
    if (SKIP.has(cursor.tagName)) return true;
    if (cursor === root) break;
  }
  return false;
}
