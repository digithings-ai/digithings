/**
 * DigiThings stat-counter — animates each .stat-counter's .stat-counter__value
 * from 0 to data-target when the element scrolls into view.
 *
 * Markup contract:
 *   <div class="stat-counter" data-target="1024" data-prefix="" data-suffix="+" data-decimals="0">
 *     <span class="stat-counter__value">0</span>
 *     <span class="stat-counter__label">requests / sec</span>
 *   </div>
 *
 * No-fake-data policy (EVOLUTION.md §10, anti-pattern #2): this module only
 * counts up to whatever data-target says — wire real numbers there via
 * props/CMS data, don't invent placeholder metrics that look live.
 *
 * Usage:
 *   import { initStatCounter } from './stat-counter.js';
 *   const ctl = initStatCounter({ selector: '.stat-counter' });
 *
 * Honors prefers-reduced-motion: renders the final value immediately with
 * no animation loop and no IntersectionObserver.
 *
 * Returns { stop() } to disconnect the observer.
 */
export function initStatCounter({
  selector = '.stat-counter',
  valueSelector = '.stat-counter__value',
  duration = 1200,
  threshold = 0.6,
} = {}) {
  const roots = document.querySelectorAll(selector);
  const reduceMotion = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const format = (root, value) => {
    const decimals = parseInt(root.dataset.decimals ?? '0', 10);
    const prefix = root.dataset.prefix ?? '';
    const suffix = root.dataset.suffix ?? '';
    return `${prefix}${value.toFixed(decimals)}${suffix}`;
  };

  const setFinal = (root) => {
    const valueEl = root.querySelector(valueSelector);
    if (!valueEl) return;
    const target = parseFloat(root.dataset.target ?? '0');
    valueEl.textContent = format(root, target);
  };

  if (reduceMotion || !('IntersectionObserver' in window)) {
    roots.forEach(setFinal);
    return { stop() {} };
  }

  const animate = (root) => {
    const valueEl = root.querySelector(valueSelector);
    if (!valueEl) return;
    const target = parseFloat(root.dataset.target ?? '0');
    const start = performance.now();

    const frame = (now) => {
      const progress = Math.min(1, (now - start) / duration);
      const eased = 1 - (1 - progress) ** 3; // ease-out-cubic
      valueEl.textContent = format(root, target * eased);
      if (progress < 1) requestAnimationFrame(frame);
    };
    requestAnimationFrame(frame);
  };

  const observer = new IntersectionObserver(
    (entries, obs) => {
      for (const entry of entries) {
        if (entry.isIntersecting) {
          animate(entry.target);
          obs.unobserve(entry.target);
        }
      }
    },
    { threshold },
  );

  roots.forEach((root) => observer.observe(root));

  return {
    stop() {
      observer.disconnect();
    },
  };
}
