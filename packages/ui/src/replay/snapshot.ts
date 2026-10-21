/**
 * Turn a rendered chat page into one offline HTML file.
 *
 * The file is the live DOM: same classes, same open and closed disclosures.
 * Disclosures become `<details>` so they still open offline. The composer
 * and anything that sends a message are removed. No script is added.
 */

import { redactHtml } from "./redact";

export const SNAPSHOT_CSS = `
details > summary { list-style: none; cursor: pointer; }
details > summary::-webkit-details-marker { display: none; }
:is(.aui-theme-stage, [data-thread-skin="digichat"]) details[open] > summary
  [data-slot="disclosure-chevron"] [data-slot="dot-matrix-grid"],
details[open] > summary .tc-caret,
details[open] > summary .tc-caret [data-slot="dot-matrix-grid"] {
  transform: rotate(90deg);
}
details:not([open]) > summary .tc-caret.open { transform: none; }
[data-snapshot-static] { cursor: default; pointer-events: none; }
`.trim();

const REMOVE = [
  ".aui-composer-root",
  "[data-slot='aui_composer-shell']",
  "[data-slot='aui_composer-editing']",
  ".aui-assistant-action-bar-root",
  ".aui-user-action-bar-root",
  ".aui-user-action-bar-slot",
  "[data-slot='aui_user-branch-picker']",
  "[data-slot='aui_assistant-branch-picker']",
  ".aui-thread-scroll-to-bottom",
  "script",
  "noscript",
  "iframe",
  "object",
  "embed",
  "link",
  "base",
  "style",
  "nextjs-portal",
  "#__next-build-watcher",
].join(",");

const CONTENT_LINK = [
  ".aui-user-message-content",
  ".aui-assistant-message-content",
  "[data-slot='aui_assistant-message-content']",
  "[data-slot='aui_user-message-content']",
  "[data-slot='reasoning-content']",
  "[data-slot='tool-fallback-content']",
  "[data-slot='tool-fallback-result']",
  "[data-slot='tool-group-content']",
  "[data-slot='aui_work-chain-content']",
  "[data-slot='aui_source-url']",
  "[data-slot='aui_source-document']",
  ".aui-md",
].join(",");

const USER_QUESTION = ".aui-user-message-content, [data-slot='aui_user-message-content']";

const PANEL_STYLE_PROPS = [
  "height",
  "width",
  "max-height",
  "min-height",
  "overflow",
  "content-visibility",
  "animation",
  "transition",
];

export function questionText(root: ParentNode): string {
  const nodes = root.querySelectorAll(USER_QUESTION);
  return nodes[nodes.length - 1]?.textContent?.replace(/\s+/g, " ").trim() ?? "";
}

export function deploymentText(root: ParentNode): string {
  return root.querySelector("[data-deployment]")?.getAttribute("data-deployment")?.trim() ?? "";
}

/** Mutates `root` into a read-only snapshot of itself. */
export function transformSnapshotDom(root: HTMLElement): void {
  root.querySelectorAll(REMOVE).forEach((node) => node.remove());
  root.querySelectorAll("[data-nextjs-dialog-overlay], [data-nextjs-toast]").forEach((node) => {
    node.remove();
  });
  convertDisclosures(root);
  freezeChrome(root);
}

export function serializeSnapshot(root: HTMLElement, css: string): string {
  const doc = root.ownerDocument;
  const head = ensureHead(root);
  head.querySelectorAll("style, link, base").forEach((node) => node.remove());
  head
    .querySelectorAll("meta[http-equiv='Content-Security-Policy' i], meta[http-equiv='refresh' i]")
    .forEach((node) => node.remove());
  if (!head.querySelector("meta[charset]")) {
    const meta = doc.createElement("meta");
    meta.setAttribute("charset", "utf-8");
    head.prepend(meta);
  }
  const style = doc.createElement("style");
  style.setAttribute("data-snapshot-css", "");
  style.textContent = `${css}\n${SNAPSHOT_CSS}`;
  head.append(style);
  const html = root.tagName === "HTML" ? root.outerHTML : `<html>${root.outerHTML}</html>`;
  return redactHtml(`<!DOCTYPE html>\n${html}`);
}

function ensureHead(root: HTMLElement): HTMLElement {
  const existing = root.querySelector(":scope > head");
  if (existing instanceof HTMLElement) return existing;
  const head = root.ownerDocument.createElement("head");
  root.prepend(head);
  return head;
}

function convertDisclosures(root: HTMLElement): void {
  const triggers = [...root.querySelectorAll<HTMLElement>("[aria-expanded]")]
    .filter((trigger) => root.contains(trigger) && isChatDisclosure(trigger))
    .sort((a, b) => depth(b) - depth(a));
  for (const trigger of triggers) {
    if (!root.contains(trigger)) continue;
    convertDisclosure(root, trigger);
  }
}

function isChatDisclosure(trigger: Element): boolean {
  const slot = trigger.getAttribute("data-slot") ?? "";
  if (slot.endsWith("-trigger") || trigger.classList.contains("tc-head")) return true;
  return trigger.querySelector("[data-slot='disclosure-chevron']") !== null;
}

function convertDisclosure(root: HTMLElement, trigger: HTMLElement): void {
  const panel = findPanel(root, trigger);
  if (!panel || panel.contains(trigger)) return;
  const host = trigger.parentElement;
  if (!host || !root.contains(host)) return;
  const details = trigger.ownerDocument.createElement("details");
  copyAttrs(host, details, false);
  if (disclosureOpen(trigger)) details.setAttribute("open", "");
  const summary = trigger.ownerDocument.createElement("summary");
  copyAttrs(trigger, summary, true);
  while (trigger.firstChild) summary.append(trigger.firstChild);
  const leftovers = [...host.childNodes].filter((node) => node !== trigger);
  host.replaceWith(details);
  details.append(summary);
  for (const node of leftovers) details.append(node);
  unlockPanel(panel);
  if (!details.contains(panel)) details.append(panel);
}

function findPanel(root: ParentNode, trigger: Element): HTMLElement | null {
  const id = trigger.getAttribute("aria-controls");
  if (id) {
    const found = root.querySelector<HTMLElement>(`[id="${cssEscape(id)}"]`);
    if (found && found !== trigger && !found.contains(trigger)) return found;
  }
  if (trigger.classList.contains("tc-head")) {
    const next = trigger.nextElementSibling;
    if (next instanceof HTMLElement) return next;
  }
  const next = trigger.nextElementSibling;
  if (next instanceof HTMLElement && looksLikePanel(next)) return next;
  const parent = trigger.parentElement;
  if (!parent) return null;
  for (const child of parent.children) {
    if (child !== trigger && child instanceof HTMLElement && looksLikePanel(child)) return child;
  }
  return null;
}

function looksLikePanel(el: Element): boolean {
  const slot = el.getAttribute("data-slot") ?? "";
  return slot.endsWith("-content") || slot === "collapsible-content";
}

function disclosureOpen(trigger: Element): boolean {
  if (trigger.getAttribute("aria-expanded") === "true") return true;
  if (trigger.hasAttribute("data-panel-open")) return true;
  if (trigger.getAttribute("data-state") === "open") return true;
  const host = trigger.parentElement;
  return Boolean(host?.hasAttribute("data-open") && !host.hasAttribute("data-closed"));
}

function unlockPanel(panel: HTMLElement): void {
  panel.hidden = false;
  panel.removeAttribute("inert");
  for (const name of ["data-closed", "data-open", "data-starting-style", "data-ending-style"]) {
    panel.removeAttribute(name);
  }
  const style = panel.getAttribute("style");
  if (!style) return;
  const next = style
    .split(";")
    .map((part) => part.trim())
    .filter((part) => {
      const prop = part.split(":")[0]?.trim().toLowerCase() ?? "";
      if (!part || PANEL_STYLE_PROPS.includes(prop)) return false;
      return !prop.startsWith("--collapsible-panel");
    })
    .join("; ");
  if (next) panel.setAttribute("style", next);
  else panel.removeAttribute("style");
}

function freezeChrome(root: HTMLElement): void {
  root.querySelectorAll("textarea, input, select").forEach((node) => node.remove());
  root.querySelectorAll("[contenteditable='true']").forEach((node) => {
    node.removeAttribute("contenteditable");
  });
  root.querySelectorAll("form").forEach((form) => {
    form.removeAttribute("action");
    form.removeAttribute("method");
  });
  for (const button of [...root.querySelectorAll("button")]) freezeControl(button);
  for (const link of [...root.querySelectorAll("a")]) freezeLink(link);
  stripHandlers(root);
}

function freezeControl(el: Element): void {
  const span = el.ownerDocument.createElement("span");
  copyAttrs(el, span, true);
  span.setAttribute("data-snapshot-static", "");
  while (el.firstChild) span.append(el.firstChild);
  el.replaceWith(span);
}

function freezeLink(link: Element): void {
  const href = link.getAttribute("href") ?? "";
  if (href.toLowerCase().startsWith("javascript:")) link.removeAttribute("href");
  if (link.closest(CONTENT_LINK)) return;
  link.removeAttribute("href");
  link.removeAttribute("target");
  link.setAttribute("data-snapshot-static", "");
}

function stripHandlers(root: HTMLElement): void {
  const elements = [root, ...root.querySelectorAll("*")];
  for (const el of elements) {
    for (const attr of [...el.attributes]) {
      if (attr.name.toLowerCase().startsWith("on")) el.removeAttribute(attr.name);
    }
  }
}

function copyAttrs(from: Element, to: Element, trigger: boolean): void {
  for (const attr of from.attributes) {
    const name = attr.name.toLowerCase();
    if (name.startsWith("on") || name === "hidden" || name === "style") continue;
    if (name.startsWith("aria-") && name !== "aria-label") continue;
    if (
      name === "type" ||
      name === "disabled" ||
      name === "tabindex" ||
      name === "role" ||
      name === "href" ||
      name === "src"
    ) {
      continue;
    }
    if (
      !trigger &&
      (name === "data-open" ||
        name === "data-closed" ||
        name === "data-state" ||
        name === "data-panel-open")
    ) {
      continue;
    }
    to.setAttribute(attr.name, attr.value);
  }
}

function depth(el: Element): number {
  let n = 0;
  let cursor: Element | null = el;
  while (cursor) {
    n += 1;
    cursor = cursor.parentElement;
  }
  return n;
}

function cssEscape(value: string): string {
  if (typeof CSS !== "undefined" && typeof CSS.escape === "function") return CSS.escape(value);
  return value.replace(/["\\]/g, "\\$&");
}
