/**
 * atlas.html — page entry module.
 *
 * Lightweight compared to digiquant main.js: hero curve draw-in + metric
 * counters, both from the shared page-motion module.
 */
import { initCounters, initDrawIn } from './page-motion.js';

document.addEventListener('DOMContentLoaded', () => {
  initDrawIn('.atl-draw-in', { duration: 2200 });
  initCounters({ duration: 900 });
});
