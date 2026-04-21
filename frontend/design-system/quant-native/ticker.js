/* ==========================================================================
   @digithings/design-system — quant-native/ticker
   --------------------------------------------------------------------------
   JS-driven horizontal ticker. No CSS marquee — we translate on a RAF loop
   so the cadence is deterministic and pause-on-hover is trivial.

   Usage:
     import { initTicker } from '@digithings/design-system/quant-native';
     import '@digithings/design-system/quant-native/styles.css';

     initTicker({
       elementId: 'ticker',
       symbols: [{ sym: 'ATLAS', price: '184.22', delta: '+0.42%' }],
       cadence: 60,  // px/sec
     });
   ========================================================================== */

function buildRow(symbols) {
  const frag = document.createDocumentFragment();
  for (const s of symbols) {
    const item = document.createElement('span');
    item.className = 'qn-ticker-item';
    const dir = typeof s.delta === 'string' && s.delta.trim().startsWith('-') ? 'down' : 'up';
    item.innerHTML = `
      <span class="qn-ticker-sym">${s.sym}</span>
      <span class="qn-metric qn-ticker-px">${s.price}</span>
      <span class="qn-${dir} qn-ticker-delta">${s.delta}</span>
    `;
    frag.appendChild(item);
  }
  return frag;
}

export function initTicker({ elementId, symbols, cadence = 60 } = {}) {
  const host = document.getElementById(elementId);
  if (!host) throw new Error(`initTicker: no element with id "${elementId}"`);
  if (!Array.isArray(symbols) || symbols.length === 0) return { destroy() {} };

  const prefersReduced = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  host.classList.add('qn-ticker');
  host.innerHTML = '';
  const track = document.createElement('div');
  track.className = 'qn-ticker-track';
  // Duplicate so the seam is always off-screen.
  track.appendChild(buildRow(symbols));
  track.appendChild(buildRow(symbols));
  host.appendChild(track);

  let offset = 0;
  let last = 0;
  let raf = 0;
  let paused = false;

  function measureHalf() {
    // Total track width / 2 — equals one full sequence.
    return track.scrollWidth / 2;
  }

  function frame(now) {
    if (!last) last = now;
    const dt = (now - last) / 1000;
    last = now;
    if (!paused) {
      offset += cadence * dt;
      const half = measureHalf();
      if (offset >= half) offset -= half;
      track.style.transform = `translateX(${-offset}px)`;
    }
    raf = requestAnimationFrame(frame);
  }

  if (prefersReduced) {
    track.style.transform = 'translateX(0)';
  } else {
    raf = requestAnimationFrame(frame);
  }

  const onEnter = () => { paused = true; };
  const onLeave = () => { paused = false; last = 0; };
  host.addEventListener('mouseenter', onEnter);
  host.addEventListener('mouseleave', onLeave);

  return {
    destroy() {
      if (raf) cancelAnimationFrame(raf);
      host.removeEventListener('mouseenter', onEnter);
      host.removeEventListener('mouseleave', onLeave);
      host.innerHTML = '';
      host.classList.remove('qn-ticker');
    },
  };
}
