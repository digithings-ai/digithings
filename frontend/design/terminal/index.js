/* ==========================================================================
   @digithings/design — terminal
   --------------------------------------------------------------------------
   Reusable terminal widget. Typewriter rendering of a scripted line list.
   Line kinds: prompt | output | comment | tool-call.
   Optional `lang` hint flips a pre-tagged highlighted span set in after
   the keystroke stream completes.

   Usage:
     import { initTerminal } from '@digithings/design/terminal';
     import '@digithings/design/terminal/styles.css';

     const term = initTerminal({
       elementId: 'term',
       lines: [
         { kind: 'prompt',   text: 'digithings init' },
         { kind: 'output',   text: 'ready.' },
         { kind: 'comment',  text: 'tooling ok' },
         { kind: 'tool-call', text: 'digigraph.route' },
       ],
       speed: 'normal',
       onReady: () => {},
     });
   ========================================================================== */

const SPEED_PRESETS = { fast: 12, normal: 32, slow: 60 };

function sleep(ms) { return new Promise((r) => setTimeout(r, ms)); }
function rand(a, b) { return a + Math.random() * (b - a); }

function resolveSpeed(speed) {
  if (typeof speed === 'number' && Number.isFinite(speed)) return speed;
  return SPEED_PRESETS[speed] ?? SPEED_PRESETS.normal;
}

function lineNodeFor(line) {
  const row = document.createElement('div');
  row.className = `term-line term-${line.kind || 'output'}`;
  const body = document.createElement('span');
  body.className = 'term-body-text';
  if (line.kind === 'prompt') {
    const marker = document.createElement('span');
    marker.className = 'term-marker';
    marker.textContent = '>';
    row.appendChild(marker);
  } else if (line.kind === 'comment') {
    const marker = document.createElement('span');
    marker.className = 'term-comment-marker';
    marker.textContent = '//';
    row.appendChild(marker);
  } else if (line.kind === 'tool-call') {
    row.classList.add('term-chip-row');
  }
  row.appendChild(body);
  return { row, body };
}

export function initTerminal({ elementId, lines, speed, onReady } = {}) {
  const host = document.getElementById(elementId);
  if (!host) throw new Error(`initTerminal: no element with id "${elementId}"`);
  host.classList.add('term-root');

  const prefersReduced = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const perChar = resolveSpeed(speed);
  const queue = Array.isArray(lines) ? lines.slice() : [];

  // Window chrome — optional; only rendered if host is empty.
  if (!host.querySelector('.term-window')) {
    const win = document.createElement('div');
    win.className = 'term-window';
    const chrome = document.createElement('div');
    chrome.className = 'term-header';
    const title = document.createElement('span');
    title.className = 'term-title';
    title.textContent = host.dataset.title || 'digithings';
    const shortcuts = document.createElement('span');
    shortcuts.className = 'term-shortcuts';
    const kbd = document.createElement('kbd');
    kbd.textContent = '⌘K';
    shortcuts.appendChild(kbd);
    chrome.appendChild(title);
    chrome.appendChild(shortcuts);
    const bodyWrap = document.createElement('div');
    bodyWrap.className = 'term-pane';
    win.appendChild(chrome);
    win.appendChild(bodyWrap);
    host.appendChild(win);
  }
  const pane = host.querySelector('.term-pane');

  async function typeInto(el, text) {
    if (prefersReduced) { el.textContent = text; return; }
    el.textContent = '';
    for (const ch of text) {
      el.textContent += ch;
      let d = rand(perChar * 0.6, perChar * 1.8);
      if (ch === ' ') d *= 0.5;
      if ('.?!,'.includes(ch)) d += 120;
      // yield to layout
      // eslint-disable-next-line no-await-in-loop
      await sleep(d);
    }
  }

  async function renderLine(line) {
    const { row, body } = lineNodeFor(line);
    pane.appendChild(row);
    await typeInto(body, line.text || '');
    // After streaming, if a lang hint is set, swap in naive highlighted markup.
    // naiveHighlight escapes source text before injecting span wrappers (DESLOP-027).
    if (line.lang && /^(js|ts|tsx|py|sh|json)$/i.test(line.lang)) {
      body.innerHTML = naiveHighlight(line.text || '', line.lang.toLowerCase());
    }
  }

  async function run() {
    for (const line of queue) {
      // eslint-disable-next-line no-await-in-loop
      await renderLine(line);
    }
    if (typeof onReady === 'function') {
      try { onReady(); } catch (_) { /* swallow */ }
    }
  }

  run().catch(() => {});

  return {
    append(line) {
      if (line && typeof line === 'object') renderLine(line).catch(() => {});
    },
    clear() { pane.innerHTML = ''; },
    destroy() {
      host.innerHTML = '';
      host.classList.remove('term-root');
    },
  };
}

/* Hand-tagged highlighter — not a real parser, just enough token coverage to
   make the detail-panel snippets read like a code editor. Tokens map to the
   per-module accent palette in tokens.css; CSS in terminal/styles.css owns
   the colors. */
const KEYWORDS = {
  js:   /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|throw|try|catch|finally)\b/g,
  ts:   /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type|enum|public|private|readonly|throw|try|catch|finally|as)\b/g,
  tsx:  /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type|throw|try|catch|finally)\b/g,
  py:   /\b(def|return|if|elif|else|for|while|class|import|from|as|try|except|finally|with|lambda|async|await|True|False|None|yield|raise|not|or|and|in|is|pass|global|nonlocal)\b/g,
  sh:   /\b(if|then|else|fi|for|do|done|while|case|esac|function|return|export|echo|cd|source)\b/g,
  json: /\b(true|false|null)\b/g,
};

// Builtins / common types — rendered as a separate token class so they read
// distinct from control-flow keywords. Matters most for Python type
// annotations (`dict[str, Any]`, `frozenset`, `Optional`, etc.).
const BUILTINS = {
  py: /\b(str|int|float|bool|bytes|dict|list|tuple|set|frozenset|Any|Optional|Union|Callable|Type|None|Self|object|range|len|print|isinstance|issubclass|enumerate|zip|map|filter)\b/g,
  ts: /\b(string|number|boolean|void|never|any|unknown|Promise|Record|Partial|Readonly|Pick|Omit|Array|Map|Set|Date|Request|Response|JSON|Math)\b/g,
  tsx: /\b(string|number|boolean|void|any|unknown|Promise|Record|Partial|Readonly)\b/g,
  js:  null,
  sh:  null,
  json: null,
};

export function escapeHtml(s) {
  return String(s).replace(/[&<>"']/g, (c) => ({
    '&': '&amp;',
    '<': '&lt;',
    '>': '&gt;',
    '"': '&quot;',
    "'": '&#39;',
  }[c]));
}

// Replace matches outside any existing <span ...> ... </span> so we never
// double-tag content already wrapped by an earlier pass.
function replaceOutsideSpans(html, regex, wrap) {
  let out = '';
  let i = 0;
  const tagRe = /<span\b[^>]*>[\s\S]*?<\/span>/g;
  let m;
  while ((m = tagRe.exec(html)) !== null) {
    const before = html.slice(i, m.index);
    out += before.replace(regex, wrap);
    out += m[0];
    i = m.index + m[0].length;
  }
  out += html.slice(i).replace(regex, wrap);
  return out;
}

export function naiveHighlight(text, lang) {
  let out = escapeHtml(text);

  // 1. Strings — first, they swallow other tokens inside.
  out = out.replace(
    /(["'`])((?:\\.|(?!\1).)*)\1/g,
    (m) => `<span class="term-tok-str">${m}</span>`,
  );

  // 2. Line comments — must be tagged before keywords so keyword
  //    matches inside comments don't fire.
  if (lang === 'py' || lang === 'sh') {
    out = replaceOutsideSpans(
      out,
      /(^|[^&])(#[^\n]*)/g,
      (_, lead, cmt) => `${lead}<span class="term-tok-cmt">${cmt}</span>`,
    );
  } else if (lang !== 'json') {
    out = replaceOutsideSpans(
      out,
      /(^|[^:])(\/\/[^\n]*)/g,
      (_, lead, cmt) => `${lead}<span class="term-tok-cmt">${cmt}</span>`,
    );
  }

  // 3. Decorators (Python @decorator).
  if (lang === 'py') {
    out = replaceOutsideSpans(
      out,
      /(^|\s)(@\w[\w.]*)/g,
      (_, lead, dec) => `${lead}<span class="term-tok-dec">${dec}</span>`,
    );
  }

  // 4. Numbers.
  out = replaceOutsideSpans(
    out,
    /\b(\d+(?:\.\d+)?)\b/g,
    '<span class="term-tok-num">$1</span>',
  );

  // 5. Keywords.
  const kw = KEYWORDS[lang];
  if (kw) {
    out = replaceOutsideSpans(out, kw, '<span class="term-tok-kw">$&</span>');
  }

  // 6. Builtins / types.
  const bi = BUILTINS[lang];
  if (bi) {
    out = replaceOutsideSpans(out, bi, '<span class="term-tok-type">$&</span>');
  }

  // 7. Type-annotation operators (Python `->`, `|`).
  if (lang === 'py' || lang === 'ts' || lang === 'tsx') {
    out = replaceOutsideSpans(
      out,
      /(-&gt;|\|)/g,
      '<span class="term-tok-op">$&</span>',
    );
  }

  return out;
}
