/**
 * digichat popup widget launcher (#3421).
 *
 * Usage (host page):
 *   <script
 *     src="https://digithings.ai/widget.js"
 *     data-host="digithings.ai"
 *     data-mode="dot"
 *     data-page-context="1"
 *     async
 *   ></script>
 *
 * Modes: data-mode="dot" (default) | "bar"
 * Optional: data-origin, data-token, data-theme, data-accent, data-page-context
 *
 * Opens a bottom-right panel that iframes /embed?layout=embed. Same tenant
 * registry / RAG corpus as full-page embed. When data-page-context=1, after
 * digichat:ready the launcher posts a structurally sanitized HTML snapshot of
 * already-visible DOM (plus visible text) — never scrapes hidden/password
 * controls or `data-digichat-private` regions. Keep the walk in sync with
 * `src/lib/page-context-sanitize.ts` (#3602).
 */
(function () {
  "use strict";

  var READY = "digichat:ready";
  var PAGE_CONTEXT = "digichat:page-context";
  var ROOT_ID = "digichat-popup-root";
  var PANEL_ID = "digichat-popup-panel";
  var BTN_ID = "digichat-popup-launcher";
  var IFRAME_ID = "digichat-popup-iframe";

  if (typeof document === "undefined") return;
  if (document.getElementById(ROOT_ID)) return;

  // Capture while currentScript is still set (before any deferred boot).
  var script =
    document.currentScript ||
    (function () {
      var scripts = document.getElementsByTagName("script");
      for (var i = scripts.length - 1; i >= 0; i--) {
        var s = scripts[i];
        var src = s.getAttribute("src") || "";
        if (/widget\.js(\?|$)/.test(src)) return s;
      }
      return null;
    })();
  if (!script) return;

  function attr(name) {
    var v = script.getAttribute(name);
    return v && v.trim() ? v.trim() : "";
  }

  function originFromSrc(src) {
    try {
      var u = new URL(src, window.location.href);
      if (u.protocol !== "http:" && u.protocol !== "https:") return "";
      return u.origin;
    } catch (e) {
      return "";
    }
  }

  var origin = (attr("data-origin") || attr("data-digichat-origin") || originFromSrc(script.src || "")).replace(
    /\/$/,
    "",
  );
  var host = attr("data-host") || attr("data-embed-host");
  if (!origin || !host) {
    if (typeof console !== "undefined") {
      console.warn("[digichat widget] missing data-host or digichat origin");
    }
    return;
  }

  var token = attr("data-token") || attr("data-embed-token");
  var mode = (attr("data-mode") || attr("data-launcher") || "dot").toLowerCase() === "bar" ? "bar" : "dot";
  var theme = attr("data-theme").toLowerCase();
  if (theme !== "light" && theme !== "dark") theme = "";
  var accent = attr("data-accent");
  if (accent && !/^#[0-9a-fA-F]{6}$/.test(accent)) accent = "";
  var pageContextOn =
    attr("data-page-context") === "1" || attr("data-page-context").toLowerCase() === "true";
  // Keep in sync with DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS /
  // MAX_PAGE_CONTEXT_TEXT_CHARS (8k) — embed rejects longer text.
  var maxChars = parseInt(attr("data-page-context-max-chars") || "8000", 10);
  if (!isFinite(maxChars) || maxChars < 1) maxChars = 8000;
  if (maxChars > 8000) maxChars = 8000;

  function buildSrc() {
    var url = new URL(origin + "/embed");
    url.searchParams.set("host", host);
    url.searchParams.set("layout", "embed");
    if (token) url.searchParams.set("token", token);
    if (theme) url.searchParams.set("theme", theme);
    if (accent) url.searchParams.set("accent", accent);
    return url.toString();
  }

  var maxHtmlChars = 12000;
  var PRIVATE_ATTR = "data-digichat-private";
  var ALLOWED_TAGS = {
    a: 1, abbr: 1, article: 1, aside: 1, b: 1, blockquote: 1, br: 1, button: 1,
    caption: 1, code: 1, dd: 1, details: 1, dfn: 1, div: 1, dl: 1, dt: 1, em: 1,
    figcaption: 1, figure: 1, footer: 1, h1: 1, h2: 1, h3: 1, h4: 1, h5: 1, h6: 1,
    header: 1, hr: 1, i: 1, label: 1, li: 1, main: 1, mark: 1, nav: 1, ol: 1, p: 1,
    pre: 1, s: 1, section: 1, small: 1, span: 1, strong: 1, sub: 1, summary: 1,
    sup: 1, table: 1, tbody: 1, td: 1, tfoot: 1, th: 1, thead: 1, time: 1, tr: 1,
    u: 1, ul: 1,
  };
  var ALLOWED_ATTRS = {
    id: 1, class: 1, role: 1, title: 1, lang: 1, dir: 1,
    "aria-label": 1, "aria-labelledby": 1, "aria-describedby": 1,
    "aria-expanded": 1, "aria-current": 1, "aria-level": 1,
    colspan: 1, rowspan: 1, scope: 1, headers: 1, datetime: 1, for: 1, href: 1,
  };
  var DROP_TAGS = {
    script: 1, style: 1, noscript: 1, iframe: 1, object: 1, embed: 1, link: 1,
    meta: 1, base: 1, template: 1, svg: 1, math: 1, canvas: 1, video: 1, audio: 1,
    source: 1, track: 1, picture: 1, param: 1, applet: 1, frame: 1, frameset: 1,
    img: 1,
  };

  function tagOf(el) {
    return (el.tagName || "").toLowerCase();
  }

  function inlineHides(el) {
    var style = el.getAttribute && el.getAttribute("style");
    if (!style) return false;
    var probe = document.createElement("div");
    probe.setAttribute("style", style);
    return probe.style.display === "none" || probe.style.visibility === "hidden" || probe.style.opacity === "0";
  }

  function computedHides(el) {
    if (!window.getComputedStyle) return false;
    var cs = window.getComputedStyle(el);
    if (cs.display === "none" || cs.visibility === "hidden") return true;
    return parseFloat(cs.opacity) === 0;
  }

  function shouldDrop(el, useComputed) {
    var tag = tagOf(el);
    if (DROP_TAGS[tag]) return true;
    if (tag === "input" || tag === "textarea" || tag === "select") return true;
    if (el.hasAttribute("hidden") || el.hasAttribute("inert")) return true;
    if ((el.getAttribute("aria-hidden") || "").trim().toLowerCase() === "true") return true;
    if (el.hasAttribute(PRIVATE_ATTR)) return true;
    if (el.closest && el.closest("[data-digichat-popup]")) return true;
    if (inlineHides(el)) return true;
    return !!(useComputed && computedHides(el));
  }

  function sanitizeHref(raw) {
    var trimmed = (raw || "").trim();
    if (!trimmed) return null;
    var lower = trimmed.toLowerCase();
    if (
      lower.indexOf("javascript:") === 0 ||
      lower.indexOf("data:") === 0 ||
      lower.indexOf("vbscript:") === 0 ||
      lower.indexOf("blob:") === 0 ||
      lower.indexOf("file:") === 0
    ) {
      return null;
    }
    try {
      var u = new URL(trimmed, "https://page-context.invalid");
      if (u.protocol !== "http:" && u.protocol !== "https:") return null;
      if (u.hostname === "page-context.invalid") return u.pathname || "/";
      return u.origin + u.pathname;
    } catch (e) {
      return null;
    }
  }

  function stripAttrs(el) {
    var tag = tagOf(el);
    var attrs = el.attributes ? Array.prototype.slice.call(el.attributes) : [];
    for (var i = 0; i < attrs.length; i++) {
      var name = attrs[i].name.toLowerCase();
      if (name.indexOf("on") === 0 || !ALLOWED_ATTRS[name]) {
        el.removeAttribute(attrs[i].name);
        continue;
      }
      if (name === "href") {
        if (tag !== "a") {
          el.removeAttribute(attrs[i].name);
          continue;
        }
        var safe = sanitizeHref(attrs[i].value);
        if (safe) el.setAttribute("href", safe);
        else el.removeAttribute(attrs[i].name);
      }
    }
  }

  function unwrap(el) {
    var parent = el.parentNode;
    if (!parent) {
      if (el.remove) el.remove();
      return;
    }
    while (el.firstChild) parent.insertBefore(el.firstChild, el);
    parent.removeChild(el);
  }

  function sanitizeInPlace(el) {
    var kids = Array.prototype.slice.call(el.childNodes);
    for (var i = 0; i < kids.length; i++) {
      var child = kids[i];
      if (child.nodeType === 8) {
        if (child.parentNode) child.parentNode.removeChild(child);
        continue;
      }
      if (child.nodeType === 3) continue;
      if (child.nodeType !== 1) {
        if (child.parentNode) child.parentNode.removeChild(child);
        continue;
      }
      if (shouldDrop(child, false)) {
        if (child.remove) child.remove();
        else if (child.parentNode) child.parentNode.removeChild(child);
        continue;
      }
      stripAttrs(child);
      sanitizeInPlace(child);
      if (!ALLOWED_TAGS[tagOf(child)]) unwrap(child);
    }
  }

  function pruneFromLive(live, clone) {
    var liveKids = Array.prototype.slice.call(live.childNodes);
    var cloneKids = Array.prototype.slice.call(clone.childNodes);
    for (var i = liveKids.length - 1; i >= 0; i--) {
      var liveNode = liveKids[i];
      var cloneNode = cloneKids[i];
      if (!cloneNode || liveNode.nodeType !== 1 || cloneNode.nodeType !== 1) continue;
      if (shouldDrop(liveNode, true)) {
        if (cloneNode.remove) cloneNode.remove();
        else if (cloneNode.parentNode) cloneNode.parentNode.removeChild(cloneNode);
        continue;
      }
      pruneFromLive(liveNode, cloneNode);
    }
  }

  function capHtml(html, max) {
    if (html.length <= max) return html;
    var sliced = html.slice(0, max);
    var lastLt = sliced.lastIndexOf("<");
    var lastGt = sliced.lastIndexOf(">");
    if (lastLt > lastGt) sliced = sliced.slice(0, lastLt);
    return sliced.replace(/\s+$/, "");
  }

  function extractPageContext() {
    var root =
      document.querySelector("main") ||
      document.querySelector('[role="main"]') ||
      document.body;
    if (!root) return { html: "", text: "" };
    if (shouldDrop(root, true)) return { html: "", text: "" };
    var clone = root.cloneNode(true);
    pruneFromLive(root, clone);
    sanitizeInPlace(clone);
    var html = capHtml((clone.innerHTML || "").replace(/\n{3,}/g, "\n\n").trim(), maxHtmlChars);
    var text = ((clone.textContent || "").replace(/\s+/g, " ").trim()).slice(0, maxChars);
    return { html: html, text: text };
  }

  /** Best-effort viewport capture; fails soft (CORS / tainted canvas). */
  function captureScreenshot(cb, visibleText) {
    try {
      var w = Math.min(window.innerWidth || 800, 1280);
      var h = Math.min(window.innerHeight || 600, 900);
      var canvas = document.createElement("canvas");
      canvas.width = w;
      canvas.height = h;
      var ctx = canvas.getContext("2d");
      if (!ctx) {
        cb(undefined);
        return;
      }
      var svg =
        '<svg xmlns="http://www.w3.org/2000/svg" width="' +
        w +
        '" height="' +
        h +
        '">' +
        '<foreignObject width="100%" height="100%">' +
        '<div xmlns="http://www.w3.org/1999/xhtml" style="font:14px sans-serif;background:#fff;color:#111;padding:8px;white-space:pre-wrap;">' +
        (visibleText || "")
          .slice(0, 4000)
          .replace(/&/g, "&amp;")
          .replace(/</g, "&lt;")
          .replace(/>/g, "&gt;") +
        "</div></foreignObject></svg>";
      var img = new Image();
      img.onload = function () {
        try {
          ctx.drawImage(img, 0, 0);
          cb(canvas.toDataURL("image/png").slice(0, 400000));
        } catch (e) {
          cb(undefined);
        }
      };
      img.onerror = function () {
        cb(undefined);
      };
      img.src = "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    } catch (e) {
      cb(undefined);
    }
  }

  function mount() {
    if (document.getElementById(ROOT_ID)) return;
    if (!document.body) {
      document.addEventListener("DOMContentLoaded", mount, { once: true });
      return;
    }

    var open = false;
    var iframeLoaded = false;
    var pageContextSent = false;

    var root = document.createElement("div");
    root.id = ROOT_ID;
    root.setAttribute("data-digichat-popup", "1");

    var style = document.createElement("style");
    style.textContent =
      "#" +
      ROOT_ID +
      "{all:initial;font-family:ui-sans-serif,system-ui,sans-serif;}" +
      "#" +
      BTN_ID +
      "{position:fixed;z-index:2147483000;right:20px;bottom:20px;border:0;cursor:pointer;" +
      "box-shadow:0 8px 24px rgba(0,0,0,.18);transition:transform .15s ease,opacity .15s ease;}" +
      "#" +
      BTN_ID +
      "[data-mode=dot]{width:56px;height:56px;border-radius:999px;background:#111;color:#fff;font-size:22px;line-height:56px;text-align:center;}" +
      "#" +
      BTN_ID +
      "[data-mode=bar]{min-width:160px;height:44px;border-radius:10px;background:#111;color:#fff;padding:0 16px;font-size:14px;font-weight:600;}" +
      "#" +
      BTN_ID +
      ":hover{transform:translateY(-1px);}" +
      "#" +
      PANEL_ID +
      "{position:fixed;z-index:2147483000;right:20px;bottom:88px;width:min(400px,calc(100vw - 24px));" +
      "height:min(640px,calc(100vh - 120px));border-radius:16px;overflow:hidden;" +
      "box-shadow:0 16px 48px rgba(0,0,0,.28);background:#0b0b0c;display:none;}" +
      "#" +
      PANEL_ID +
      "[data-open=1]{display:block;}" +
      "#" +
      IFRAME_ID +
      "{width:100%;height:100%;border:0;background:transparent;}";
    root.appendChild(style);

    var btn = document.createElement("button");
    btn.id = BTN_ID;
    btn.type = "button";
    btn.setAttribute("data-mode", mode);
    btn.setAttribute("aria-label", "Open digichat");
    btn.setAttribute("aria-expanded", "false");
    btn.setAttribute("aria-controls", PANEL_ID);
    btn.textContent = mode === "bar" ? "Ask digichat" : "✦";
    if (accent) btn.style.background = accent;

    var panel = document.createElement("div");
    panel.id = PANEL_ID;
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", "digichat");

    var iframe = document.createElement("iframe");
    iframe.id = IFRAME_ID;
    iframe.title = "digichat";
    iframe.allow = "clipboard-write";
    iframe.setAttribute("loading", "lazy");

    panel.appendChild(iframe);
    root.appendChild(panel);
    root.appendChild(btn);
    document.body.appendChild(root);

    function sendPageContext() {
      if (!pageContextOn || pageContextSent) return;
      var win = iframe.contentWindow;
      if (!win) return;
      var ctx = extractPageContext();
      var text = ctx.text;
      var html = ctx.html;
      captureScreenshot(function (shot) {
        var payload = {
          type: PAGE_CONTEXT,
          text: text,
          ts: Date.now(),
        };
        if (html) payload.html = html;
        if (shot) payload.screenshotDataUrl = shot;
        try {
          win.postMessage(payload, origin);
          pageContextSent = true;
        } catch (e) {
          /* ignore — allow retry on next ready */
        }
      }, text);
    }

    function setOpen(next) {
      open = next;
      panel.setAttribute("data-open", open ? "1" : "0");
      btn.setAttribute("aria-expanded", open ? "true" : "false");
      btn.setAttribute("aria-label", open ? "Close digichat" : "Open digichat");
      if (open && !iframeLoaded) {
        iframe.src = buildSrc();
        iframeLoaded = true;
      }
    }

    btn.addEventListener("click", function () {
      setOpen(!open);
    });

    window.addEventListener("message", function (ev) {
      if (ev.origin !== origin) return;
      var data = ev.data;
      if (!data || data.type !== READY) return;
      sendPageContext();
    });

    document.addEventListener("keydown", function (ev) {
      if (ev.key === "Escape" && open) setOpen(false);
    });
  }

  mount();
})();
