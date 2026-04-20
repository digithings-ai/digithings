/* ==========================================================================
   @digithings/design-system — terminal
   --------------------------------------------------------------------------
   Reusable terminal widget. Typewriter rendering of a scripted line list.
   Line kinds: prompt | output | comment | tool-call.
   Optional `lang` hint flips a pre-tagged highlighted span set in after
   the keystroke stream completes.

   Usage:
     import { initTerminal } from '@digithings/design-system/terminal';
     import '@digithings/design-system/terminal/styles.css';

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
    shortcuts.innerHTML = '<kbd>⌘K</kbd>';
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

/* Naive hand-tagged highlighter — not a real tokenizer. Just colors keywords,
   strings, and numbers. Good enough for decorative terminal transcripts. */
const KEYWORDS = {
  js: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined)\b/g,
  ts: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type|enum|public|private|readonly)\b/g,
  tsx: /\b(const|let|var|function|return|if|else|for|while|class|new|import|from|export|default|async|await|true|false|null|undefined|interface|type)\b/g,
  py: /\b(def|return|if|elif|else|for|while|class|import|from|as|try|except|finally|with|lambda|async|await|True|False|None|yield|raise)\b/g,
  sh: /\b(if|then|else|fi|for|do|done|while|case|esac|function|return|export|echo|cd|source)\b/g,
  json: /\b(true|false|null)\b/g,
};

function escapeHtml(s) {
  return s.replace(/[&<>]/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;' }[c]));
}

export function naiveHighlight(text, lang) {
  let out = escapeHtml(text);
  // strings
  out = out.replace(/(["'`])((?:\\.|(?!\1).)*)\1/g, (m) => `<span class="term-tok-str">${m}</span>`);
  // numbers
  out = out.replace(/\b(\d+(?:\.\d+)?)\b/g, '<span class="term-tok-num">$1</span>');
  // keywords
  const kw = KEYWORDS[lang];
  if (kw) out = out.replace(kw, '<span class="term-tok-kw">$&</span>');
  // line comments (only after string/keyword pass for js-like langs)
  if (lang !== 'json') {
    if (lang === 'py' || lang === 'sh') {
      out = out.replace(/(^|\s)(#[^\n]*)/g, '$1<span class="term-tok-cmt">$2</span>');
    } else {
      out = out.replace(/(^|\s)(\/\/[^\n]*)/g, '$1<span class="term-tok-cmt">$2</span>');
    }
  }
  return out;
}
