/**
 * DigiThings scroll-trigger — writes a 0..1 progress value to `--scroll`
 * on every element matching `selector` as the user scrolls.
 *
 * Markup contract (unchanged from original website/main.js):
 *   <div class="scroll-trigger" data-direction="bottom|left|right|zoom">
 *
 * CSS consumes `--scroll` (see components.css) to translate/scale/blur.
 *
 * Usage:
 *   import { initScrollTrigger } from './scroll-trigger.js';
 *   const ctl = initScrollTrigger({
 *     selector: '.scroll-trigger',
 *     revealThreshold: 0.85,
 *     onProgress: (el, progress) => {  // optional per-element callback
 *       if (el.classList.contains('hero-visual') && progress > 0.5) ...
 *     },
 *     activateSelector: '.timeline-event',
 *     activationLineRatio: 0.7,
 *   });
 *
 * Returns { stop() } to cancel the loop.
 */
export function initScrollTrigger({
  selector = '.scroll-trigger',
  revealThreshold = 0.85,
  onProgress = null,
  activateSelector = null,
  activationLineRatio = 0.7,
} = {}) {
  const triggers = document.querySelectorAll(selector);
  const activators = activateSelector
    ? document.querySelectorAll(activateSelector)
    : [];

  let rafId = null;
  let frameCount = 0;
  let running = true;

  const loop = () => {
    if (!running) return;
    frameCount += 1;

    if (frameCount % 2 === 0) {
      const windowHeight = window.innerHeight;
      const activationLine = windowHeight * activationLineRatio;
      const fullyRevealedAt = windowHeight * (1 - revealThreshold);

      for (let i = 0; i < triggers.length; i++) {
        const el = triggers[i];
        const rect = el.getBoundingClientRect();
        const distanceFromBottom = windowHeight - rect.top;
        let progress = 0;
        if (distanceFromBottom > 0 && fullyRevealedAt > 0) {
          progress = Math.min(1, Math.max(0, distanceFromBottom / fullyRevealedAt));
        }
        if (rect.top <= 0) progress = 1;
        el.style.setProperty('--scroll', progress);
        if (onProgress) onProgress(el, progress, rect);
      }

      for (let i = 0; i < activators.length; i++) {
        const el = activators[i];
        const rect = el.getBoundingClientRect();
        if (rect.top < activationLine) {
          el.classList.add('active');
        } else {
          el.classList.remove('active');
        }
      }
    }

    rafId = requestAnimationFrame(loop);
  };

  rafId = requestAnimationFrame(loop);

  return {
    stop() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
    },
  };
}
