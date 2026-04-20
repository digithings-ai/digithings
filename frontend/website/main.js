/**
 * digithings.ai landing page — loader.
 *
 * Thin composition layer that initializes the extracted design-system
 * modules, plus three restrained page-level interactions:
 *
 * 1. Sequenced card reveal — 80ms stagger on `.module-grid .module-card`
 *    scroll-trigger transitions, indexed per grid.
 * 2. Magnetic-hover on `.hero-cta` — cursor-tracked translate up to 3px.
 * 3. (CSS-only) Accent-trace perimeter draw on `.module-card` hover —
 *    defined in components.css; no JS.
 *
 * All three respect `prefers-reduced-motion`.
 */
import { initStarfield } from '../design-system/starfield.js';
import { initScrollTrigger } from '../design-system/scroll-trigger.js';
import { typeWriter } from '../design-system/typewriter.js';

const TERMINAL_CODE =
  'from digithings import digigraph\n\n' +
  '# Initialize orchestrator\n' +
  'agent = digigraph(mode="secure")\n\n' +
  '# Connect execution engine\n' +
  'agent.attach("nautilus_core")\n\n' +
  'agent.run()';

const STAGGER_MS = 80;
const MAGNET_MAX_PX = 3;

function prefersReducedMotion() {
  return window.matchMedia?.('(prefers-reduced-motion: reduce)').matches === true;
}

/**
 * Apply an index-based `transition-delay` to each card in a grid so that
 * when the grid enters the viewport, cards cascade in.
 */
function applyStaggeredReveal() {
  if (prefersReducedMotion()) return;
  document.querySelectorAll('.module-grid').forEach((grid) => {
    const cards = grid.querySelectorAll('.module-card');
    cards.forEach((card, i) => {
      card.style.transitionDelay = `${i * STAGGER_MS}ms`;
    });
  });
}

/**
 * Attach a `mousemove` listener to each `.hero-cta` so the button
 * translates up to 3px toward the cursor within its own bounds.
 */
function attachMagneticHover() {
  if (prefersReducedMotion()) return;
  document.querySelectorAll('.hero-cta').forEach((cta) => {
    cta.addEventListener('mousemove', (event) => {
      const rect = cta.getBoundingClientRect();
      const cx = rect.left + rect.width / 2;
      const cy = rect.top + rect.height / 2;
      // Fraction of distance to corner, clamped to [-1, 1], then scaled.
      const dx = Math.max(-1, Math.min(1, (event.clientX - cx) / (rect.width / 2))) * MAGNET_MAX_PX;
      const dy = Math.max(-1, Math.min(1, (event.clientY - cy) / (rect.height / 2))) * MAGNET_MAX_PX;
      cta.style.transform = `translate3d(${dx}px, ${dy}px, 0)`;
    });
    cta.addEventListener('mouseleave', () => {
      cta.style.transform = '';
    });
  });
}

document.addEventListener('DOMContentLoaded', () => {
  initStarfield({ canvasId: 'network-canvas' });

  applyStaggeredReveal();
  attachMagneticHover();

  let typeWriterStarted = false;
  const heroVisual = document.querySelector('.hero-visual.scroll-trigger');

  initScrollTrigger({
    selector: '.scroll-trigger',
    revealThreshold: 0.85,
    activateSelector: '.timeline-event',
    activationLineRatio: 0.7,
    onProgress: (el, progress) => {
      if (el === heroVisual && progress > 0.5 && !typeWriterStarted) {
        typeWriterStarted = true;
        setTimeout(() => {
          typeWriter('typewriter-code', TERMINAL_CODE, { speed: 30 });
        }, 400);
      }
    },
  });
});
