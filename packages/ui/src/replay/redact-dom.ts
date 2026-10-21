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

/**
 * A block is re-scanned as one string unless it contains one of these.
 * `del` (strikethrough), `ins`, `img`, `label` and `font` are not block
 * elements, so a secret split by them is still joined.
 */
const BLOCK = new Set([
  "ADDRESS",
  "ARTICLE",
  "ASIDE",
  "BLOCKQUOTE",
  "DD",
  "DIV",
  "DL",
  "DT",
  "FIELDSET",
  "FIGCAPTION",
  "FIGURE",
  "FOOTER",
  "FORM",
  "H1",
  "H2",
  "H3",
  "H4",
  "H5",
  "H6",
  "HEADER",
  "HR",
  "LI",
  "MAIN",
  "NAV",
  "OL",
  "P",
  "PRE",
  "SECTION",
  "TABLE",
  "UL",
  "TR",
  "TD",
  "TH",
  "THEAD",
  "TBODY",
  "TFOOT",
  "CAPTION",
]);

/** Text that is not page prose: CSS and math. SVG text is page content. */
const SKIP = new Set(["STYLE", "SCRIPT", "MATH", "math"]);

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
  redactTree(root);
}

/**
 * `<template>` content is a document fragment, not a child of the element, so
 * a walk of the page never sees it. SVG used to be skipped with `<style>`.
 */
function redactTree(root: ParentNode): void {
  redactAttributes(root);
  redactTexts(root);
  for (const block of inlineOnlyBlocks(root)) {
    const text = block.textContent ?? "";
    const next = redactBlockText(text);
    if (next !== text) block.textContent = next;
  }
  for (const template of root.querySelectorAll("template")) {
    if (template instanceof HTMLTemplateElement) redactTree(template.content);
  }
}

function redactTexts(root: ParentNode): void {
  const doc = root.ownerDocument;
  if (!doc) return;
  // Every text node first: a secret inside one node is replaced in place, so
  // links and formatting around it survive.
  const walker = doc.createTreeWalker(root, 4 /* NodeFilter.SHOW_TEXT */);
  const texts: Text[] = [];
  for (let node = walker.nextNode(); node; node = walker.nextNode()) texts.push(node as Text);
  for (const node of texts) {
    if (insideSkipped(node.parentElement, root)) continue;
    const next = redactString(node.data);
    if (next !== node.data) node.data = next;
  }
}

function redactAttributes(root: ParentNode): void {
  const elements: Element[] = [];
  if (root instanceof Element) elements.push(root);
  elements.push(...root.querySelectorAll("*"));
  for (const el of elements) {
    if (SKIP.has(el.tagName)) continue;
    for (const attr of [...el.attributes]) {
      const value = attr.value;
      // style holds inlined url(data:…) payloads; data: URIs are the inlined assets.
      if (!value || attr.name === "style" || isInlinedAsset(attr.name, value)) continue;
      const next = redactString(value);
      if (next !== value) el.setAttribute(attr.name, next);
    }
  }
}

/**
 * The outermost elements whose whole subtree is inline and holds text: a `p`,
 * `pre`, `li`, a JSON view, or an inline run beside block siblings.
 */
function inlineOnlyBlocks(root: ParentNode): Element[] {
  const elements: Element[] = [];
  if (root instanceof Element) elements.push(root);
  elements.push(...root.querySelectorAll("*"));
  const candidates = elements.filter((el) => {
    if (SKIP.has(el.tagName) || insideSkipped(el.parentElement, root)) return false;
    if (!el.textContent?.trim()) return false;
    for (const d of el.querySelectorAll("*")) {
      if (BLOCK.has(d.tagName) || SKIP.has(d.tagName)) return false;
    }
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

/** Base64 image and font payloads. Any other `data:` value is still redacted. */
function isInlinedAsset(name: string, value: string): boolean {
  const attr = name.toLowerCase();
  if (attr !== "src" && attr !== "href" && attr !== "poster") return false;
  return /^\s*data:(?:image|font)\/[^;,]*;base64,/i.test(value);
}

function insideSkipped(el: Element | null, stop: Node): boolean {
  for (let cursor = el; cursor; cursor = cursor.parentElement) {
    if (SKIP.has(cursor.tagName)) return true;
    if (cursor === stop) break;
  }
  return false;
}
