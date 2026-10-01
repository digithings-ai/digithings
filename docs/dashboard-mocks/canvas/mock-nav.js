/* digiquant canvas — nav locks (#4911)
 * - digichat opens a right rail; never replaces the digiquant left spine
 * - left rail is resizable; narrow width collapses to a mini icon rail
 * - Cmd/Ctrl-K opens the shortcut palette; ↑/↓ cycle pages
 */
(function () {
  "use strict";

  var STORAGE_W = "dq-canvas-rail-w";
  var STORAGE_CHAT = "dq-canvas-chat-open";
  var MINI_AT = 88;
  var MIN_W = 56;
  var MAX_W = 360;
  var DEFAULT_W = 208;

  var PAGES = [
    { path: "/1/brief", href: "brief.html", label: "brief" },
    { path: "/1/book", href: "brief-book.html", label: "brief book" },
    { path: "/1/markets", href: "brief-markets.html", label: "brief markets" },
    { path: "/1/chart", href: "brief-chart.html", label: "brief chart" },
    { path: "/2/holdings", href: "holdings.html", label: "holdings" },
    { path: "/3/theses", href: "theses.html", label: "theses" },
    { path: "/4/tearsheet", href: "tearsheet.html", label: "tearsheet" },
    { path: "/5/ledger", href: "ledger.html", label: "ledger" },
    { path: "/6/pipeline", href: "pipeline.html", label: "pipeline" },
    { path: "/7/strategies", href: "strategies.html", label: "strategies" },
    { path: "/8/terminal", href: "gloomberg.html", label: "terminal" },
    { path: "/9/luxalgo", href: "luxalgo.html", label: "luxalgo" },
    { path: "/10/charts", href: "charts.html", label: "charts" },
    { path: "/11/fx-hub", href: "fx-hub.html", label: "fx-hub" },
    { path: "/12/settings", href: "settings.html", label: "settings" }
  ];

  function fileName() {
    var p = (location.pathname || "").split("/").pop() || "index.html";
    return p || "index.html";
  }

  function pageIndex() {
    var f = fileName();
    for (var i = 0; i < PAGES.length; i++) {
      if (PAGES[i].href === f) return i;
    }
    // portfolio cousins
    if (f === "attribution.html" || f === "holdings-empty.html") return 1;
    if (f === "ledger-error.html") return 4;
    if (f === "brief-book.html") return 1;
    if (f === "brief-markets.html") return 2;
    if (f === "brief-chart.html") return 3;
    if (f.indexOf("brief") === 0) return 0;
    if (f.indexOf("pipeline") === 0) return 5;
    if (f.indexOf("strategy") === 0) return 6;
    if (f.indexOf("fx-") === 0) return 10;
    if (f.indexOf("settings") === 0) return 11;
    if (f === "chat.html" || f === "chat-fullscreen.html") return -1;
    return -1;
  }

  function applyRailWidth(px) {
    var w = Math.max(MIN_W, Math.min(MAX_W, px | 0));
    document.documentElement.style.setProperty("--rail", w + "px");
    document.documentElement.classList.toggle("rail-mini", w <= MINI_AT);
    try { localStorage.setItem(STORAGE_W, String(w)); } catch (e) {}
    return w;
  }

  function ensureResizeHandle() {
    var app = document.querySelector(".app");
    var side = document.querySelector("aside.side");
    if (!app || !side || side.querySelector(".rail-resize")) return;
    var handle = document.createElement("div");
    handle.className = "rail-resize";
    handle.setAttribute("role", "separator");
    handle.setAttribute("aria-orientation", "vertical");
    handle.setAttribute("aria-label", "Resize digiquant nav");
    handle.tabIndex = 0;
    side.appendChild(handle);

    var dragging = false;
    function onMove(ev) {
      if (!dragging) return;
      var x = ev.clientX != null ? ev.clientX : (ev.touches && ev.touches[0] && ev.touches[0].clientX);
      if (x == null) return;
      var left = app.getBoundingClientRect().left;
      applyRailWidth(x - left);
    }
    function onUp() {
      if (!dragging) return;
      dragging = false;
      document.documentElement.classList.remove("rail-resizing");
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    }
    handle.addEventListener("pointerdown", function (ev) {
      ev.preventDefault();
      dragging = true;
      document.documentElement.classList.add("rail-resizing");
      window.addEventListener("pointermove", onMove);
      window.addEventListener("pointerup", onUp);
    });
    handle.addEventListener("keydown", function (ev) {
      var cur = parseInt(getComputedStyle(document.documentElement).getPropertyValue("--rail"), 10) || DEFAULT_W;
      if (ev.key === "ArrowLeft") { applyRailWidth(cur - 16); ev.preventDefault(); }
      if (ev.key === "ArrowRight") { applyRailWidth(cur + 16); ev.preventDefault(); }
    });
  }

  function ensureChatRail() {
    var app = document.querySelector(".app");
    if (!app) return null;
    var existing = document.querySelector("aside.dock, aside.chat-rail");
    if (existing) {
      existing.classList.add("chat-rail");
      return existing;
    }
    var rail = document.createElement("aside");
    rail.className = "chat-rail dock";
    rail.setAttribute("aria-label", "digichat");
    rail.hidden = true;
    rail.innerHTML =
      '<header class="band"><div class="eyebrow"><i class="tick"></i><span>digichat</span></div>' +
      '<h1>Research chat</h1><div class="meta"><span class="badge wip">wip</span>' +
      '<button type="button" class="lnk chat-close" aria-label="Close digichat">close</button></div></header>' +
      '<div class="transcript">' +
      '<div class="bubble you"><div class="who">you</div><div class="doc"><p>Why did the run hold?</p></div></div>' +
      '<div class="bubble bot"><div class="who">digichat</div><div class="doc"><h3>digichat</h3>' +
      '<p>The run kept every active thesis. Duration stays the largest tilt. One mark (DBC) was unavailable.</p>' +
      '<p class="soft">Right rail only — digiquant left nav stays. Open <a class="lnk" href="chat.html">chat desk</a> or <a class="lnk" href="chat-fullscreen.html">full thread</a>.</p>' +
      '</div></div></div>' +
      '<div class="composer"><input disabled placeholder="Message digichat (mock)" aria-label="Message digichat"></div>';
    app.appendChild(rail);
    return rail;
  }

  function setChatOpen(open) {
    var rail = ensureChatRail();
    if (!rail) return;
    var on = !!open;
    document.documentElement.classList.toggle("chat-open", on);
    if (rail.classList.contains("dock") && fileName() === "chat.html") {
      rail.hidden = false;
    } else {
      rail.hidden = !on;
    }
    try { localStorage.setItem(STORAGE_CHAT, on ? "1" : "0"); } catch (e) {}
    document.querySelectorAll("[data-chat-toggle]").forEach(function (el) {
      el.setAttribute("aria-pressed", on ? "true" : "false");
      if (on) el.setAttribute("aria-current", "true");
      else el.removeAttribute("aria-current");
    });
  }

  function toggleChat() {
    var open = document.documentElement.classList.contains("chat-open");
    setChatOpen(!open);
  }

  function ensurePalette() {
    if (document.getElementById("dq-palette")) return;
    var wrap = document.createElement("div");
    wrap.id = "dq-palette";
    wrap.className = "palette";
    wrap.hidden = true;
    wrap.setAttribute("role", "dialog");
    wrap.setAttribute("aria-label", "Shortcut palette");
    var list = PAGES.map(function (p, i) {
      return '<button type="button" class="palette-item" data-i="' + i + '" data-href="' + p.href + '">' +
        '<span class="n">' + p.path + '</span><span class="lbl">' + p.label + '</span></button>';
    }).join("");
    wrap.innerHTML =
      '<div class="palette-card">' +
      '<div class="palette-head"><span class="k">go to</span>' +
      '<input class="palette-input" type="search" placeholder="/path or name · ↑↓ enter · esc" aria-label="Filter pages"></div>' +
      '<div class="palette-list">' + list + '</div>' +
      '<div class="palette-foot"><span>⌘K / Ctrl+K</span><span>← → cycle pages</span><span>digichat = right rail</span></div>' +
      '</div>';
    document.body.appendChild(wrap);

    var input = wrap.querySelector(".palette-input");
    var items = [].slice.call(wrap.querySelectorAll(".palette-item"));
    var active = 0;

    function paint() {
      items.forEach(function (el, i) {
        el.classList.toggle("is-active", i === active && el.style.display !== "none");
      });
    }
    function visibleItems() {
      return items.filter(function (el) { return el.style.display !== "none"; });
    }
    function filter(q) {
      q = (q || "").trim().toLowerCase();
      items.forEach(function (el) {
        var href = el.getAttribute("data-href");
        var path = el.querySelector(".n").textContent;
        var lbl = el.querySelector(".lbl").textContent;
        var ok = !q || path.indexOf(q) >= 0 || lbl.indexOf(q) >= 0 || href.indexOf(q) >= 0;
        el.style.display = ok ? "" : "none";
      });
      var vis = visibleItems();
      active = vis.length ? items.indexOf(vis[0]) : 0;
      paint();
    }
    function open() {
      wrap.hidden = false;
      document.documentElement.classList.add("palette-open");
      filter("");
      input.value = "";
      setTimeout(function () { input.focus(); }, 0);
    }
    function close() {
      wrap.hidden = true;
      document.documentElement.classList.remove("palette-open");
    }
    function go(i) {
      var el = items[i];
      if (!el || el.style.display === "none") return;
      location.href = el.getAttribute("data-href");
    }

    wrap.addEventListener("click", function (ev) {
      if (ev.target === wrap) close();
      var btn = ev.target.closest(".palette-item");
      if (btn) go(items.indexOf(btn));
    });
    input.addEventListener("input", function () { filter(input.value); });
    input.addEventListener("keydown", function (ev) {
      var vis = visibleItems();
      if (ev.key === "Escape") { close(); ev.preventDefault(); }
      if (ev.key === "ArrowDown") {
        var ni = vis[Math.min(vis.length - 1, Math.max(0, vis.indexOf(items[active]) + 1))];
        if (ni) active = items.indexOf(ni);
        paint(); ev.preventDefault();
      }
      if (ev.key === "ArrowUp") {
        var pi = vis[Math.max(0, vis.indexOf(items[active]) - 1)];
        if (pi) active = items.indexOf(pi);
        paint(); ev.preventDefault();
      }
      if (ev.key === "Enter") { go(active); ev.preventDefault(); }
    });

    window.__dqPalette = { open: open, close: close, toggle: function () { wrap.hidden ? open() : close(); } };
  }

  function wireNav() {
    document.querySelectorAll("[data-chat-toggle]").forEach(function (el) {
      el.addEventListener("click", function (ev) {
        ev.preventDefault();
        toggleChat();
      });
    });
    var rail = document.querySelector(".chat-rail, aside.dock");
    if (rail) {
      var closer = rail.querySelector(".chat-close");
      if (closer) closer.addEventListener("click", function () { setChatOpen(false); });
    }
  }



  function wireDeskExpand() {
    document.querySelectorAll("[data-desk-expand]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        ev.stopPropagation();
        openDeskOverlay();
      });
    });
    document.querySelectorAll("[data-desk-collapse]").forEach(function (btn) {
      btn.addEventListener("click", function () { closeDeskOverlay(); });
    });
  }

  function openDeskOverlay() {
    var overlay = document.querySelector("[data-desk-overlay]");
    if (!overlay) return;
    var optsHost = overlay.querySelector("[data-desk-opts]");
    var menu = document.querySelector(".deskpick .deskmenu");
    if (optsHost && menu && !optsHost.dataset.filled) {
      optsHost.innerHTML = "";
      menu.querySelectorAll("a.opt").forEach(function (a) {
        var clone = a.cloneNode(true);
        optsHost.appendChild(clone);
      });
      optsHost.dataset.filled = "1";
    }
    overlay.hidden = false;
    document.documentElement.classList.add("desk-fs");
  }

  function closeDeskOverlay() {
    var overlay = document.querySelector("[data-desk-overlay]");
    if (overlay) overlay.hidden = true;
    document.documentElement.classList.remove("desk-fs");
  }


  /* ── pane rearrange (polish dump) ── */
  var PANE_ORDER_KEY = "dq-canvas-pane-order:";

  function paneOrderKey() {
    return PANE_ORDER_KEY + fileName();
  }

  function wirePaneRearrange() {
    var col = document.querySelector("main.main > .col");
    if (!col) return;
    col.classList.add("col-stretch");

    // Restore order from sessionStorage
    try {
      var saved = sessionStorage.getItem(paneOrderKey());
      if (saved) {
        var ids = JSON.parse(saved);
        if (Array.isArray(ids) && ids.length) {
          ids.forEach(function (id) {
            var el = col.querySelector('.sec[data-pane-id="' + id + '"]');
            if (el) col.appendChild(el);
          });
          // keep footer last
          var foot = col.querySelector("footer.foot");
          if (foot) col.appendChild(foot);
        }
      }
    } catch (e) {}

    var dragSec = null;

    function persist() {
      var ids = [];
      col.querySelectorAll(".sec[data-pane-id]").forEach(function (s) {
        ids.push(s.getAttribute("data-pane-id"));
      });
      try { sessionStorage.setItem(paneOrderKey(), JSON.stringify(ids)); } catch (e) {}
    }

    col.querySelectorAll(".sec[data-pane-id]").forEach(function (sec) {
      sec.setAttribute("draggable", "true");
      var handle = sec.querySelector("[data-pane-drag]");
      if (handle) {
        handle.addEventListener("pointerdown", function () {
          sec.setAttribute("draggable", "true");
        });
      }
      sec.addEventListener("dragstart", function (ev) {
        dragSec = sec;
        sec.classList.add("is-dragging");
        col.classList.add("rearranging");
        try {
          ev.dataTransfer.effectAllowed = "move";
          ev.dataTransfer.setData("text/plain", sec.getAttribute("data-pane-id") || "");
        } catch (e) {}
      });
      sec.addEventListener("dragend", function () {
        sec.classList.remove("is-dragging");
        col.classList.remove("rearranging");
        col.querySelectorAll(".sec.drag-over").forEach(function (s) {
          s.classList.remove("drag-over");
        });
        dragSec = null;
        persist();
      });
      sec.addEventListener("dragover", function (ev) {
        if (!dragSec || dragSec === sec) return;
        ev.preventDefault();
        sec.classList.add("drag-over");
        try { ev.dataTransfer.dropEffect = "move"; } catch (e) {}
      });
      sec.addEventListener("dragleave", function () {
        sec.classList.remove("drag-over");
      });
      sec.addEventListener("drop", function (ev) {
        ev.preventDefault();
        sec.classList.remove("drag-over");
        if (!dragSec || dragSec === sec) return;
        var rect = sec.getBoundingClientRect();
        var before = (ev.clientY - rect.top) < rect.height / 2;
        if (before) col.insertBefore(dragSec, sec);
        else col.insertBefore(dragSec, sec.nextSibling);
        var foot = col.querySelector("footer.foot");
        if (foot) col.appendChild(foot);
        persist();
      });
    });
  }

  function wirePaneFullscreen() {
    document.querySelectorAll("[data-pane-fs]").forEach(function (btn) {
      btn.addEventListener("click", function (ev) {
        ev.preventDefault();
        var sec = btn.closest(".sec");
        if (!sec) return;
        var on = document.documentElement.classList.contains("pane-fs") && sec.classList.contains("is-fs");
        document.querySelectorAll(".sec.is-fs").forEach(function (s) { s.classList.remove("is-fs"); });
        if (on) {
          document.documentElement.classList.remove("pane-fs");
          btn.textContent = "full";
        } else {
          sec.classList.add("is-fs");
          document.documentElement.classList.add("pane-fs");
          btn.textContent = "esc";
        }
      });
    });
  }

  function closePaneFullscreen() {
    document.documentElement.classList.remove("pane-fs");
    document.querySelectorAll(".sec.is-fs").forEach(function (s) { s.classList.remove("is-fs"); });
    document.querySelectorAll("[data-pane-fs]").forEach(function (b) { b.textContent = "full"; });
  }

  function onKey(ev) {
    var tag = (ev.target && ev.target.tagName) || "";
    var typing = tag === "INPUT" || tag === "TEXTAREA" || (ev.target && ev.target.isContentEditable);
    if ((ev.metaKey || ev.ctrlKey) && (ev.key === "k" || ev.key === "K")) {
      ev.preventDefault();
      ensurePalette();
      window.__dqPalette.toggle();
      return;
    }
    if (ev.key === "Escape") {
      if (window.__dqPalette) window.__dqPalette.close();
      closeDeskOverlay();
      closePaneFullscreen();
    }
    if (typing) return;
    if (ev.key === "ArrowLeft" || ev.key === "ArrowRight") {
      var i = pageIndex();
      if (i < 0) return;
      var next = ev.key === "ArrowRight" ? (i + 1) % PAGES.length : (i - 1 + PAGES.length) % PAGES.length;
      location.href = PAGES[next].href;
      ev.preventDefault();
    }
  }


  function nearestPageScroller(from) {
    var el = from && from.parentElement;
    while (el && el !== document.documentElement) {
      if (el.matches && el.matches(".main > .col")) return el;
      var st = window.getComputedStyle(el);
      var oy = st.overflowY;
      if ((oy === "auto" || oy === "scroll" || oy === "overlay") && el.scrollHeight > el.clientHeight + 1) {
        if (!el.classList.contains("atom-chart") && !(el.matches && el.matches('.sec[data-atom="chart"] > .body'))) {
          return el;
        }
      }
      el = el.parentElement;
    }
    return document.querySelector(".main > .col") || document.scrollingElement || document.documentElement;
  }

  function wireChartWheel() {
    var roots = document.querySelectorAll('.atom-chart, .sec[data-atom="chart"], .pane.tall');
    roots.forEach(function (root) {
      root.addEventListener("wheel", function (ev) {
        // Horizontal (or mostly horizontal): leave chart pan/zoom alone
        if (Math.abs(ev.deltaX) > Math.abs(ev.deltaY)) return;
        if (!ev.deltaY) return;
        var scroller = nearestPageScroller(root);
        if (!scroller) return;
        var before = scroller.scrollTop;
        scroller.scrollTop = before + ev.deltaY;
        if (scroller.scrollTop !== before) {
          ev.preventDefault();
        } else {
          // Still block chart from eating the gesture when parent is at edge
          ev.preventDefault();
        }
      }, { passive: false });
    });
  }

  function boot() {
    var saved = DEFAULT_W;
    try {
      var s = localStorage.getItem(STORAGE_W);
      if (s) saved = parseInt(s, 10) || DEFAULT_W;
    } catch (e) {}
    applyRailWidth(saved);
    ensureResizeHandle();
    ensureChatRail();
    ensurePalette();
    wireNav();
    wireDeskExpand();
    wirePaneFullscreen();
    wirePaneRearrange();
    wireChartWheel();

    var chatPage = fileName() === "chat.html";
    var wantOpen = chatPage;
    try { if (localStorage.getItem(STORAGE_CHAT) === "1") wantOpen = true; } catch (e) {}
    if (chatPage) wantOpen = true;
    setChatOpen(wantOpen);

    document.addEventListener("keydown", onKey);
  }

  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
