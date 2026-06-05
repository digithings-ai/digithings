/**
 * DigiThings typewriter — types `text` into element `#elId` one char at a
 * time.
 *
 * Usage:
 *   import { typeWriter } from './typewriter.js';
 *   typeWriter('typewriter-code', 'hello', { speed: 30, onDone: () => {} });
 *
 * Options:
 *   speed   — ms per character. Default 30.
 *   onDone  — optional callback fired ~700ms after the last character.
 */
export function typeWriter(elId, text, opts = {}) {
  const { speed = 30, onDone } = opts;
  const el = document.getElementById(elId);
  if (!el) return;

  const step = (i) => {
    if (i < text.length) {
      el.textContent = text.substring(0, i + 1);
      setTimeout(() => step(i + 1), speed);
    } else if (typeof onDone === 'function') {
      setTimeout(onDone, 700);
    }
  };
  step(0);
}
