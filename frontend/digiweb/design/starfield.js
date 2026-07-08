/**
 * DigiThings shared starfield — cross-brand signature animation.
 *
 * Usage:
 *   import { initStarfield } from './starfield.js';
 *   initStarfield({ canvasId: 'network-canvas' });
 *
 * Options:
 *   canvasId  — DOM id of the <canvas> element to draw into. Required.
 *   density   — star count. Defaults to 180 on desktop, 80 on mobile
 *               (<= 480px wide), matching the original website behavior.
 *   theme     — `'dark'` (default, clear canvas) | `'auto'` (Olympus: fill
 *               from `html.light` / `html.dark` and star contrast).
 *
 * Returns:
 *   { stop() } — call to cancel the animation loop and detach listeners.
 *
 * Implementation notes:
 *   - Uses requestAnimationFrame.
 *   - Pauses on `visibilitychange` when the tab is hidden (power/perf).
 *   - Resizes on window resize.
 */
export function initStarfield({ canvasId, density, theme = 'dark' } = {}) {
  const canvas = document.getElementById(canvasId);
  if (!canvas) return { stop() {} };

  const ctx = canvas.getContext('2d');
  if (!ctx) return { stop() {} };

  const isMobile = window.matchMedia('(max-width: 480px)').matches;
  const N = typeof density === 'number' ? density : (isMobile ? 80 : 180);
  const themeAuto = theme === 'auto';
  const isLightRef = { current: false };

  const syncLight = () => {
    if (!themeAuto) return;
    isLightRef.current = document.documentElement.classList.contains('light');
  };
  syncLight();

  let themeObserver = null;
  if (themeAuto) {
    themeObserver = new MutationObserver(syncLight);
    themeObserver.observe(document.documentElement, { attributes: true, attributeFilter: ['class'] });
  }

  const stars = Array.from({ length: N }, () => ({
    x: Math.random(),
    y: Math.random(),
    d: Math.random(),
    ph: Math.random() * Math.PI * 2,
  }));

  let width = 0;
  let height = 0;
  let rafId = null;
  let running = true;

  const resize = () => {
    width = canvas.width = window.innerWidth;
    height = canvas.height = window.innerHeight;
  };
  resize();

  const draw = () => {
    if (!running) return;
    const light = themeAuto && isLightRef.current;
    if (themeAuto) {
      ctx.fillStyle = light ? '#f4f4f5' : '#0a0a0a';
      ctx.fillRect(0, 0, width, height);
    } else {
      ctx.clearRect(0, 0, width, height);
    }
    for (const s of stars) {
      s.ph += 0.01 + s.d * 0.015;
      const tw = 0.6 + 0.4 * Math.sin(s.ph);
      const r = 0.35 + s.d * 1.1;
      const o = 0.2 + s.d * 0.55 * tw;
      ctx.beginPath();
      ctx.fillStyle = light
        ? `rgba(24,24,27,${o * 0.85})`
        : `rgba(230,230,230,${o})`;
      ctx.arc(s.x * width, s.y * height, r, 0, Math.PI * 2);
      ctx.fill();
      s.y -= 0.00015 + s.d * 0.0002;
      if (s.y < 0) s.y = 1;
    }
    rafId = requestAnimationFrame(draw);
  };

  const onVisibility = () => {
    if (document.hidden) {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      rafId = null;
    } else if (!running) {
      running = true;
      rafId = requestAnimationFrame(draw);
    }
  };

  window.addEventListener('resize', resize);
  document.addEventListener('visibilitychange', onVisibility);
  rafId = requestAnimationFrame(draw);

  return {
    stop() {
      running = false;
      if (rafId) cancelAnimationFrame(rafId);
      window.removeEventListener('resize', resize);
      document.removeEventListener('visibilitychange', onVisibility);
      themeObserver?.disconnect();
    },
  };
}
