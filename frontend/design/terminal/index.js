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

import { escapeHtml } from '../html-escape.js';
import { mountHighlighted } from './highlight-dom.js';

export { escapeHtml };
export { mountHighlighted, buildHighlightFragment, collectHighlightSpans } from './highlight-dom.js';

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
    if (line.lang && /^(js|ts|tsx|py|sh|json)$/i.test(line.lang)) {
      mountHighlighted(body, line.text || '', line.lang.toLowerCase());
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
    clear() { pane.replaceChildren(); },
    destroy() {
      host.replaceChildren();
      host.classList.remove('term-root');
    },
  };
}
