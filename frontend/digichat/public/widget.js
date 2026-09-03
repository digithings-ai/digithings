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
 * digichat:ready the launcher posts visible document.body.innerText (already
 * shown to the visitor) — never scrapes behind auth.
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
  var maxChars = parseInt(attr("data-page-context-max-chars") || "8000", 10);
  if (!isFinite(maxChars) || maxChars < 1) maxChars = 8000;
  if (maxChars > 20000) maxChars = 20000;

  function buildSrc() {
    var url = new URL(origin + "/embed");
    url.searchParams.set("host", host);
    url.searchParams.set("layout", "embed");
    if (token) url.searchParams.set("token", token);
    if (theme) url.searchParams.set("theme", theme);
    if (accent) url.searchParams.set("accent", accent);
    return url.toString();
  }

  function extractVisibleText() {
    var raw = (document.body && document.body.innerText) || "";
    return raw.replace(/\s+/g, " ").trim().slice(0, maxChars);
  }

  /** Best-effort viewport capture; fails soft (CORS / tainted canvas). */
  function captureScreenshot(cb) {
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
        extractVisibleText()
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
    pageContextSent = true;
    var text = extractVisibleText();
    captureScreenshot(function (shot) {
      var payload = {
        type: PAGE_CONTEXT,
        text: text,
        ts: Date.now(),
      };
      if (shot) payload.screenshotDataUrl = shot;
      try {
        win.postMessage(payload, origin);
      } catch (e) {
        /* ignore */
      }
    });
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
})();
