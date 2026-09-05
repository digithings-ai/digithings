/**
 * Structural page-context sanitizer (#3602).
 *
 * Sender (dashboard popup / widget.js) clones the live DOM, drops non-visible and
 * sensitive nodes, then serializes an allowlisted fragment. Receiver (embed)
 * parses the HTML payload with DOMParser and applies the same allowlist — never
 * a regex tag strip. CSS-hidden nodes are dropped only on a live document
 * (computed style); the receiver still honors hidden / inert / aria-hidden /
 * inline display:none / the opt-out marker.
 *
 * Privacy contract: see frontend/digichat/ARCHITECTURE.md (page-context).
 * Hosts exclude regions with `data-digichat-private`.
 *
 * Keep `public/widget.js` in sync with this walk.
 */

export const PAGE_CONTEXT_PRIVATE_ATTR = "data-digichat-private";

/** Keep in sync with embed-page-context-messages caps. */
export const DEFAULT_PAGE_CONTEXT_HTML_CHARS = 12_000;
export const DEFAULT_PAGE_CONTEXT_TEXT_CHARS = 8_000;

const ALLOWED_TAGS = new Set([
  "a",
  "abbr",
  "article",
  "aside",
  "b",
  "blockquote",
  "br",
  "caption",
  "code",
  "dd",
  "details",
  "dfn",
  "div",
  "dl",
  "dt",
  "em",
  "figcaption",
  "figure",
  "footer",
  "h1",
  "h2",
  "h3",
  "h4",
  "h5",
  "h6",
  "header",
  "hr",
  "i",
  "label",
  "li",
  "main",
  "mark",
  "nav",
  "ol",
  "p",
  "pre",
  "s",
  "section",
  "small",
  "span",
  "strong",
  "sub",
  "summary",
  "sup",
  "table",
  "tbody",
  "td",
  "tfoot",
  "th",
  "thead",
  "time",
  "tr",
  "u",
  "ul",
  "button",
]);

const ALLOWED_ATTRS = new Set([
  "id",
  "class",
  "role",
  "title",
  "lang",
  "dir",
  "aria-label",
  "aria-labelledby",
  "aria-describedby",
  "aria-expanded",
  "aria-current",
  "aria-level",
  "colspan",
  "rowspan",
  "scope",
  "headers",
  "datetime",
  "for",
  "href",
]);

const DROP_TAGS = new Set([
  "script",
  "style",
  "noscript",
  "iframe",
  "object",
  "embed",
  "link",
  "meta",
  "base",
  "template",
  "svg",
  "math",
  "canvas",
  "video",
  "audio",
  "source",
  "track",
  "picture",
  "param",
  "applet",
  "frame",
  "frameset",
  "img",
]);

const SECRET_AUTOCOMPLETE = new Set([
  "current-password",
  "new-password",
  "password",
  "cc-number",
  "cc-csc",
  "cc-exp",
  "cc-exp-month",
  "cc-exp-year",
  "one-time-code",
]);

type WalkOpts = { useComputedStyle: boolean };

function defaultDocument(): Document | null {
  return typeof document !== "undefined" ? document : null;
}

function tagName(el: Element): string {
  return el.tagName.toLowerCase();
}

function inlineStyleHides(style: string | null): boolean {
  if (!style || typeof document === "undefined") return false;
  const probe = document.createElement("div");
  probe.setAttribute("style", style);
  if (probe.style.display === "none" || probe.style.visibility === "hidden") {
    return true;
  }
  return probe.style.opacity === "0";
}

function computedStyleHides(el: Element): boolean {
  const view = el.ownerDocument.defaultView;
  if (!view) return false;
  const cs = view.getComputedStyle(el);
  if (cs.display === "none" || cs.visibility === "hidden") return true;
  const opacity = Number.parseFloat(cs.opacity);
  return opacity === 0;
}

function isSensitiveControl(el: Element): boolean {
  const tag = tagName(el);
  if (tag === "input" || tag === "textarea" || tag === "select") return true;
  const ac = (el.getAttribute("autocomplete") ?? "").trim().toLowerCase();
  if (!ac) return false;
  return ac.split(/\s+/).some((t) => SECRET_AUTOCOMPLETE.has(t));
}

function isHiddenFromPresentation(el: Element, useComputed: boolean): boolean {
  if (el.hasAttribute("hidden") || el.hasAttribute("inert")) return true;
  if ((el.getAttribute("aria-hidden") ?? "").trim().toLowerCase() === "true") {
    return true;
  }
  if (el.hasAttribute(PAGE_CONTEXT_PRIVATE_ATTR)) return true;
  if (el.closest("[data-digichat-popup]")) return true;
  if (inlineStyleHides(el.getAttribute("style"))) return true;
  return useComputed && computedStyleHides(el);
}

function shouldDrop(el: Element, opts: WalkOpts): boolean {
  if (DROP_TAGS.has(tagName(el))) return true;
  if (isSensitiveControl(el)) return true;
  return isHiddenFromPresentation(el, opts.useComputedStyle);
}

function sanitizeHref(raw: string): string | null {
  const trimmed = raw.trim();
  if (!trimmed) return null;
  const lower = trimmed.toLowerCase();
  if (
    lower.startsWith("javascript:") ||
    lower.startsWith("data:") ||
    lower.startsWith("vbscript:") ||
    lower.startsWith("blob:") ||
    lower.startsWith("file:")
  ) {
    return null;
  }
  try {
    const u = new URL(trimmed, "https://page-context.invalid");
    if (u.protocol !== "http:" && u.protocol !== "https:") return null;
    if (u.hostname === "page-context.invalid") return u.pathname || "/";
    return `${u.origin}${u.pathname}`;
  } catch {
    return null;
  }
}

function stripDisallowedAttrs(el: Element): void {
  const tag = tagName(el);
  for (const attr of Array.from(el.attributes)) {
    const name = attr.name.toLowerCase();
    if (name.startsWith("on")) {
      el.removeAttribute(attr.name);
      continue;
    }
    if (!ALLOWED_ATTRS.has(name)) {
      el.removeAttribute(attr.name);
      continue;
    }
    if (name === "href") {
      if (tag !== "a") {
        el.removeAttribute(attr.name);
        continue;
      }
      const safe = sanitizeHref(attr.value);
      if (safe) el.setAttribute("href", safe);
      else el.removeAttribute(attr.name);
    }
  }
}

function unwrap(el: Element): void {
  const parent = el.parentNode;
  if (!parent) {
    el.remove();
    return;
  }
  while (el.firstChild) parent.insertBefore(el.firstChild, el);
  parent.removeChild(el);
}

function sanitizeElementInPlace(el: Element, opts: WalkOpts): void {
  const kids = Array.from(el.childNodes);
  for (const child of kids) {
    if (child.nodeType === Node.COMMENT_NODE) {
      child.parentNode?.removeChild(child);
      continue;
    }
    if (child.nodeType === Node.TEXT_NODE) continue;
    if (child.nodeType !== Node.ELEMENT_NODE) {
      child.parentNode?.removeChild(child);
      continue;
    }
    const childEl = child as Element;
    if (shouldDrop(childEl, opts)) {
      childEl.remove();
      continue;
    }
    stripDisallowedAttrs(childEl);
    sanitizeElementInPlace(childEl, opts);
    if (!ALLOWED_TAGS.has(tagName(childEl))) unwrap(childEl);
  }
}

function pruneCloneFromLive(live: Element, clone: Element): void {
  const liveKids = Array.from(live.childNodes);
  const cloneKids = Array.from(clone.childNodes);
  for (let i = liveKids.length - 1; i >= 0; i -= 1) {
    const liveNode = liveKids[i];
    const cloneNode = cloneKids[i];
    if (!cloneNode || liveNode.nodeType !== Node.ELEMENT_NODE) continue;
    if (cloneNode.nodeType !== Node.ELEMENT_NODE) continue;
    const liveEl = liveNode as Element;
    const cloneEl = cloneNode as Element;
    if (shouldDrop(liveEl, { useComputedStyle: true })) {
      cloneEl.remove();
      continue;
    }
    pruneCloneFromLive(liveEl, cloneEl);
  }
}

function capHtml(html: string, maxChars: number): string {
  if (html.length <= maxChars) return html;
  let sliced = html.slice(0, maxChars);
  const lastLt = sliced.lastIndexOf("<");
  const lastGt = sliced.lastIndexOf(">");
  if (lastLt > lastGt) sliced = sliced.slice(0, lastLt);
  return sliced.trimEnd();
}

function normalizeWs(html: string): string {
  return html.replace(/[ \t]+\n/g, "\n").replace(/\n{3,}/g, "\n\n").trim();
}

function collapseWs(text: string): string {
  return text.replace(/\s+/g, " ").trim();
}

function parseHtmlBody(raw: string): Element | null {
  if (typeof DOMParser === "undefined") return null;
  const doc = new DOMParser().parseFromString(raw, "text/html");
  return doc.body;
}

function pageContextRoot(doc: Document): Element | null {
  return doc.querySelector("main") ?? doc.querySelector("[role=main]") ?? doc.body;
}

/**
 * Parse HTML and return an allowlisted fragment. Fail closed when DOMParser
 * is missing (non-browser). Never re-hydrate the result as live DOM.
 */
export function sanitizePageHtml(
  raw: string,
  maxChars: number = DEFAULT_PAGE_CONTEXT_HTML_CHARS,
): string {
  const body = parseHtmlBody(raw);
  if (!body) return "";
  sanitizeElementInPlace(body, { useComputedStyle: false });
  return capHtml(normalizeWs(body.innerHTML), maxChars);
}

/**
 * Visible-page HTML + text from a live document. Uses computed style so
 * stylesheet-hidden nodes never enter the payload.
 */
export function extractPageContext(
  doc: Document | null = defaultDocument(),
  maxHtml: number = DEFAULT_PAGE_CONTEXT_HTML_CHARS,
  maxText: number = DEFAULT_PAGE_CONTEXT_TEXT_CHARS,
): { html: string; text: string } {
  if (!doc) return { html: "", text: "" };
  const liveRoot = pageContextRoot(doc);
  if (!liveRoot) return { html: "", text: "" };
  if (shouldDrop(liveRoot, { useComputedStyle: true })) {
    return { html: "", text: "" };
  }
  const clone = liveRoot.cloneNode(true) as Element;
  pruneCloneFromLive(liveRoot, clone);
  sanitizeElementInPlace(clone, { useComputedStyle: false });
  const html = capHtml(normalizeWs(clone.innerHTML), maxHtml);
  const text = collapseWs(clone.textContent ?? "").slice(0, maxText);
  return { html, text };
}

export function extractPageHtml(
  maxChars: number = DEFAULT_PAGE_CONTEXT_HTML_CHARS,
  doc: Document | null = defaultDocument(),
): string {
  return extractPageContext(doc, maxChars).html;
}
