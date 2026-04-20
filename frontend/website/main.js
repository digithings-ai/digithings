/**
 * digithings.ai landing page — loader.
 *
 * Thin composition layer that initializes the extracted design-system
 * modules. No feature changes vs. the pre-extraction behavior.
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

document.addEventListener('DOMContentLoaded', () => {
  initStarfield({ canvasId: 'network-canvas' });

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
