/**
 * terminal.js — typed terminal playback for the hero signature (and demos).
 *
 * typeTerminal(el, lines, opts): renders `lines` into `el` (a <pre>), revealing
 * line-by-line with a blinking cursor. Under reduced-motion it renders the full
 * transcript instantly. Authored text is escaped before injection.
 *
 * Line shape: { kind, text?, name?, copy? }
 *   kind: 'cmd' | 'out' | 'ok' | 'mod' | 'install' | 'arrow' | 'gap'
 *   - cmd:     `$ <text>`
 *   - out:     muted output line
 *   - ok:      `✓ <name>  <text>`  (service-up line; name emphasised)
 *   - mod:     `<name>  <text>  →` (module row; name in accent)
 *   - install: highlighted command; pass copy:true for a copy button
 *   - arrow:   accent summary line (text already includes the glyph)
 *   - gap:     blank line
 */
import { escapeHtml } from "../html-escape.js";

const pad = (s, n) => { s = String(s || ""); return s.length >= n ? s : s + " ".repeat(n - s.length); };

function renderLine(line) {
  const t = escapeHtml(line.text || "");
  switch (line.kind) {
    case "gap": return "\n";
    case "cmd": return `<span class="tl-cmd">${t}</span>\n`;
    case "out": return `<span class="tl-out">${t}</span>\n`;
    case "user": return `<span class="tl-user">${t}</span>\n`;
    case "comment": return `<span class="tl-comment">${t}</span>\n`;
    case "ok": return `<span class="tl-ok"><b>${escapeHtml(pad(line.name, 12))}</b>${t}</span>\n`;
    case "mod": return `<span class="tl-mod"><b>${escapeHtml(pad(line.name, 13))}</b>${t}  →</span>\n`;
    case "install":
      return `<span class="tl-install">${t}</span>` +
        (line.copy ? `<button class="term-copy" data-copy="${escapeHtml(line.text || "")}"><span data-copy-label>copy</span></button>` : "") + "\n";
    case "arrow": return `<span class="tl-arrow">${t}</span>\n`;
    default: return "";
  }
}

const CURSOR = '<span class="term-cursor"></span>';

export function typeTerminal(el, lines, opts = {}) {
  if (!el) return;
  const reduce = opts.reduceMotion ?? matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduce) {
    el.innerHTML = lines.map(renderLine).join("") + CURSOR;
    return;
  }
  let i = 0;
  const step = () => {
    el.innerHTML = lines.slice(0, i + 1).map(renderLine).join("") + (i >= lines.length - 1 ? CURSOR : "");
    const prev = lines[i];
    i++;
    if (i < lines.length) {
      const delay = prev && prev.kind === "gap" ? 90 : prev && prev.kind === "cmd" ? 430 : 200;
      setTimeout(step, delay);
    }
  };
  setTimeout(step, opts.startDelay ?? 420);
}
