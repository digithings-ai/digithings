/**
 * Shared page-motion primitives for the digiquant.io static pages.
 * One implementation for counters and the hero-curve draw-in — main.js and
 * atlas-main.js previously carried drifting copies of this code.
 */

function formatCount(value, decimals, suffix) {
  const n = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
  return suffix ? `${n}${suffix}` : n;
}

function animateCounter(el, duration) {
  if (el.dataset.countDone === '1') return;
  el.dataset.countDone = '1';
  const target   = parseFloat(el.dataset.countTo);
  const decimals = parseInt(el.dataset.countDecimals || '0', 10);
  const suffix   = el.dataset.countSuffix || '';
  if (!Number.isFinite(target)) return;

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const finalize = () => {
    el.textContent = formatCount(target, decimals, suffix);
  };
  if (prefersReduced) {
    finalize();
    return;
  }

  const start = performance.now();
  let finalized = false;
  function step(now) {
    if (finalized) return;
    const t = Math.min(1, (now - start) / duration);
    const k = 1 - Math.pow(1 - t, 3); // easeOutCubic
    el.textContent = formatCount(target * k, decimals, suffix);
    if (t < 1) {
      requestAnimationFrame(step);
    } else {
      finalized = true;
      finalize();
    }
  }
  requestAnimationFrame(step);
  // If the tab is hidden, rAF is throttled and may never tick — make sure
  // the final value lands either way.
  setTimeout(() => {
    if (finalized) return;
    finalized = true;
    finalize();
  }, duration + 200);
}

/** Animate every [data-count-to] element when it scrolls into view. */
export function initCounters({ duration = 1100 } = {}) {
  const counters = document.querySelectorAll('[data-count-to]');
  if (counters.length === 0) return;
  if (!('IntersectionObserver' in window)) {
    counters.forEach((el) => animateCounter(el, duration));
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting && entry.intersectionRatio > 0) {
        animateCounter(entry.target, duration);
        io.unobserve(entry.target);
      }
    }
  }, {
    // Lower threshold + bottom rootMargin: fires reliably even when the
    // metric row is taller than 40% of a small viewport.
    threshold: [0, 0.15],
    rootMargin: '0px 0px -8% 0px',
  });
  counters.forEach((el) => io.observe(el));
}

/** Stroke draw-in for a hero SVG path. */
export function initDrawIn(selector, { duration = 2400 } = {}) {
  const path = document.querySelector(selector);
  if (!path) return;
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const length = path.getTotalLength ? path.getTotalLength() : 2000;
  path.style.strokeDasharray = String(length);
  if (prefersReduced) {
    path.style.strokeDashoffset = '0';
    return;
  }
  path.style.strokeDashoffset = String(length);
  requestAnimationFrame(() => {
    path.style.transition = `stroke-dashoffset ${duration}ms cubic-bezier(0.2, 0.8, 0.2, 1)`;
    path.style.strokeDashoffset = '0';
  });
  setTimeout(() => {
    if (path.style.strokeDashoffset !== '0') {
      path.style.strokeDashoffset = '0';
    }
  }, duration + 200);
}
