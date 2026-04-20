/**
 * digiquant.io — entry module.
 *
 * Composes the shared starfield + scroll-trigger modules from the sibling
 * design-system directory. No DigiQuant-specific JS lives here yet; the
 * page just opts into the cross-brand signature animation.
 */
import { initStarfield } from '../design-system/starfield.js';
import { initScrollTrigger } from '../design-system/scroll-trigger.js';

initStarfield({ canvasId: 'network-canvas' });
initScrollTrigger({ selector: '.scroll-trigger' });
