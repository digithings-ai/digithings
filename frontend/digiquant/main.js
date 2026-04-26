/**
 * digiquant.io — quant-native entry module.
 *
 * Composes primitives from the design:
 *   - quant-native/ticker        → bottom-pinned symbol ribbon
 *   - typography-motion          → hero title variable-weight scroll shift
 *   - living-architecture        → Act I DigiQuant subsystem diagram
 *   - scroll-trigger             → drives counter animations + draw-ins
 *
 * No real market data. All symbols, prices, signals, and metrics are
 * synthesized for illustration only.
 */
import { initTicker } from '../design/quant-native/ticker.js';
import { initTypographyMotion } from '../design/typography-motion/index.js';
import { initDiagram } from '../design/living-architecture/index.js';
import { initScrollTrigger } from '../design/scroll-trigger.js';

// --- Ticker symbols (synthesized; no real tickers) -----------------------
const TICKER_SYMBOLS = [
  { sym: 'DIGI', price: '128.4', delta: '+0.8%' },
  { sym: 'QNT1', price: '22.11', delta: '-0.2%' },
  { sym: 'ATL',  price: '3.42',  delta: '+1.1%' },
  { sym: 'KRS',  price: '0.88',  delta: '-0.4%' },
  { sym: 'HRM',  price: '17.5',  delta: '+0.3%' },
  { sym: 'GRFX', price: '94.2',  delta: '+0.9%' },
  { sym: 'SRCH', price: '55.0',  delta: '+0.0%' },
];

// --- Living-architecture nodes for Act I ---------------------------------
// DigiQuant root + Atlas / Hermes / Kairos children + NautilusTrader callout.
const ARCH_NODES = [
  { id: 'dq',       label: 'DigiQuant',     x: 500, y: 110, accentVar: '--accent-digiquant', group: 'core' },
  { id: 'atlas',    label: 'Atlas',         x: 230, y: 290, accentVar: '--accent-atlas' },
  { id: 'hermes',   label: 'Hermes',        x: 500, y: 320, accentVar: '--accent-hermes' },
  { id: 'kairos',   label: 'Kairos',        x: 770, y: 290, accentVar: '--accent-kairos' },
  { id: 'nautilus', label: 'NautilusTrader', x: 500, y: 460, accentVar: '--accent-digiquant' },
];
const ARCH_EDGES = [
  { source: 'dq',      target: 'atlas' },
  { source: 'dq',      target: 'hermes' },
  { source: 'dq',      target: 'kairos' },
  { source: 'atlas',   target: 'hermes' },
  { source: 'hermes',  target: 'kairos' },
  { source: 'kairos',  target: 'nautilus' },
  { source: 'hermes',  target: 'nautilus' },
];

// --- Counter animation ---------------------------------------------------
function formatCount(value, decimals, suffix) {
  const n = decimals > 0 ? value.toFixed(decimals) : String(Math.round(value));
  return suffix ? `${n}${suffix}` : n;
}

function animateCounter(el) {
  if (el.dataset.countDone === '1') return;
  el.dataset.countDone = '1';
  const target   = parseFloat(el.dataset.countTo);
  const decimals = parseInt(el.dataset.countDecimals || '0', 10);
  const suffix   = el.dataset.countSuffix || '';
  if (!Number.isFinite(target)) return;

  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  if (prefersReduced) {
    el.textContent = formatCount(target, decimals, suffix);
    return;
  }

  const duration = 1100;
  const start = performance.now();
  const finalize = () => {
    el.textContent = formatCount(target, decimals, suffix);
  };
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
  // Belt-and-suspenders: if the tab was hidden when init fired, rAF is
  // throttled and the chain above may never run a single frame. The
  // setTimeout below guarantees the final value lands either way.
  // (Real animation still wins when the tab is foreground because rAF
  // ticks well before this fires.)
  setTimeout(() => {
    if (finalized) return;
    finalized = true;
    finalize();
  }, duration + 200);
}

function initCounters() {
  const counters = document.querySelectorAll('[data-count-to]');
  if (counters.length === 0) return;
  if (!('IntersectionObserver' in window)) {
    counters.forEach(animateCounter);
    return;
  }
  const io = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (entry.isIntersecting && entry.intersectionRatio > 0) {
        animateCounter(entry.target);
        io.unobserve(entry.target);
      }
    }
  }, {
    // Lower threshold + bottom rootMargin: fires reliably even when the
    // metric row is short (threshold: 0.4 missed it on screens where the
    // row is more than 40% tall vs the viewport).
    threshold: [0, 0.15],
    rootMargin: '0px 0px -8% 0px',
  });
  counters.forEach((el) => io.observe(el));
}

// --- Draw-in on scroll for the hero equity curve -------------------------
function initDrawIn() {
  const path = document.querySelector('.dq-draw-in');
  if (!path) return;
  const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const length = path.getTotalLength ? path.getTotalLength() : 2000;
  path.style.strokeDasharray = String(length);
  if (prefersReduced) {
    path.style.strokeDashoffset = '0';
    return;
  }
  path.style.strokeDashoffset = String(length);
  // Kick off shortly after load for a dignified reveal.
  requestAnimationFrame(() => {
    path.style.transition = 'stroke-dashoffset 2400ms cubic-bezier(0.2, 0.8, 0.2, 1)';
    path.style.strokeDashoffset = '0';
  });
}

// --- Composite toggles (Act V) -------------------------------------------
function initCompositeToggles() {
  const toggles = document.querySelectorAll('.dq-toggle');
  const composite = document.querySelector('.dq-composite');
  if (!composite || toggles.length === 0) return;
  toggles.forEach((btn) => {
    btn.addEventListener('click', () => {
      toggles.forEach((b) => b.classList.remove('is-on'));
      btn.classList.add('is-on');
      composite.setAttribute('data-composite-mode', btn.dataset.mode || 'plug');
    });
  });
}

// --- Candle hover highlight (Act II) -------------------------------------
function initCandleHover() {
  document.querySelectorAll('.dq-candle-group g').forEach((g) => {
    g.addEventListener('mouseenter', () => g.classList.add('is-hover'));
    g.addEventListener('mouseleave', () => g.classList.remove('is-hover'));
  });
}

// --- Boot ----------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
  // Ticker — pinned ribbon.
  try {
    initTicker({ elementId: 'dq-ticker', symbols: TICKER_SYMBOLS, cadence: 40 });
  } catch (err) { console.warn('[digiquant] ticker init failed', err); }

  // Typography motion — hero weight shift on scroll.
  try { initTypographyMotion(); } catch (err) { console.warn('[digiquant] typo-motion failed', err); }

  // Living-architecture — Act I diagram.
  try {
    initDiagram({
      hostId: 'dq-arch-host',
      svgId:  'dq-arch-svg',
      nodes:  ARCH_NODES,
      edges:  ARCH_EDGES,
    });
  } catch (err) { console.warn('[digiquant] arch init failed', err); }

  // Scroll-trigger — powers reveal progress vars.
  try { initScrollTrigger({ selector: '.scroll-trigger' }); } catch (_) { /* optional */ }

  initDrawIn();
  initCounters();
  initCompositeToggles();
  initCandleHover();
});
