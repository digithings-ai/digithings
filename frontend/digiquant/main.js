/**
 * digiquant.io — quant-native entry module.
 *
 * Composes primitives from the design package:
 *   - typography-motion          → hero title variable-weight scroll shift
 *   - living-architecture        → Act I DigiQuant subsystem diagram
 *
 * Charts and metrics on this page are illustrative and labeled as such in
 * the markup; nothing here claims to be live data. The live surface is the
 * Olympus dashboard at /olympus/.
 */
import { initTypographyMotion } from '../design/typography-motion/index.js';
import { initDiagram } from '../design/living-architecture/index.js';
import { initCounters, initDrawIn } from './page-motion.js';

// --- Living-architecture nodes for Act I ---------------------------------
// DigiQuant root + Atlas / Hermes children + planned Kairos + NautilusTrader.
const ARCH_NODES = [
  { id: 'dq',       label: 'DigiQuant',        x: 500, y: 110, accentVar: '--accent-digiquant', group: 'core' },
  { id: 'atlas',    label: 'Atlas',            x: 230, y: 290, accentVar: '--accent-atlas' },
  { id: 'hermes',   label: 'Hermes',           x: 500, y: 320, accentVar: '--accent-hermes' },
  { id: 'kairos',   label: 'Kairos · planned', x: 770, y: 290, accentVar: '--accent-kairos' },
  { id: 'nautilus', label: 'NautilusTrader',   x: 500, y: 460, accentVar: '--accent-digiquant' },
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

// --- Act V tabs: real tab semantics, real panel switching -----------------
function initModeTabs() {
  const tabs = Array.from(document.querySelectorAll('.dq-toggle[role="tab"]'));
  const panels = Array.from(document.querySelectorAll('.dq-composite-panel[role="tabpanel"]'));
  if (tabs.length === 0 || panels.length === 0) return;

  function select(tab) {
    tabs.forEach((t) => {
      const on = t === tab;
      t.classList.toggle('is-on', on);
      t.setAttribute('aria-selected', String(on));
      t.tabIndex = on ? 0 : -1;
    });
    panels.forEach((p) => {
      p.hidden = p.id !== tab.getAttribute('aria-controls');
    });
  }

  tabs.forEach((tab, i) => {
    tab.addEventListener('click', () => select(tab));
    tab.addEventListener('keydown', (e) => {
      const dir = e.key === 'ArrowRight' ? 1 : e.key === 'ArrowLeft' ? -1 : 0;
      if (!dir) return;
      e.preventDefault();
      const next = tabs[(i + dir + tabs.length) % tabs.length];
      next.focus();
      select(next);
    });
  });

  // Roving tabindex from first paint, not just after the first interaction.
  const initial = tabs.find((t) => t.getAttribute('aria-selected') === 'true') || tabs[0];
  select(initial);
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

  initDrawIn('.dq-draw-in');
  initCounters();
  initModeTabs();
  initCandleHover();
});
