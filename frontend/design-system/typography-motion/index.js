/* ==========================================================================
   @digithings/design-system — typography-motion
   --------------------------------------------------------------------------
   Bind scroll progress to variable-font weight and letter-spacing.
   Two usage modes:

   1) Imperative — attach to a specific element:
        import { attachWeightShift } from '@digithings/design-system/typography-motion';
        const handle = attachWeightShift(el, { from: 200, to: 700, scrollStart: 0, scrollEnd: 400 });
        handle.detach();

   2) Declarative — mark up elements, call init() once:
        <h1 class="tws-weight-shift" data-weight-from="200" data-weight-to="700"></h1>
        <h2 class="tws-tracking-shift" data-tracking-from="-0.01" data-tracking-to="-0.05"></h2>
        import { initTypographyMotion } from '@digithings/design-system/typography-motion';
        initTypographyMotion();
   ========================================================================== */

const prefersReduced = () => typeof window !== 'undefined'
  && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

function clamp01(x) { return Math.max(0, Math.min(1, x)); }

function progressForRange(scrollStart, scrollEnd) {
  const y = window.scrollY;
  const span = Math.max(1, scrollEnd - scrollStart);
  return clamp01((y - scrollStart) / span);
}

function attachRangeBinding(el, { from, to, scrollStart, scrollEnd, apply }) {
  if (prefersReduced()) {
    apply(to);
    return { detach() {} };
  }
  let raf = 0;
  function tick() {
    raf = 0;
    const p = progressForRange(scrollStart, scrollEnd);
    apply(from + (to - from) * p);
  }
  function onScroll() {
    if (raf) return;
    raf = requestAnimationFrame(tick);
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  tick();
  return {
    detach() {
      window.removeEventListener('scroll', onScroll);
      if (raf) cancelAnimationFrame(raf);
    },
  };
}

export function attachWeightShift(el, { from = 200, to = 700, scrollStart = 0, scrollEnd = 400 } = {}) {
  if (!el) throw new Error('attachWeightShift: element is required');
  el.classList.add('tws-weight-shift');
  return attachRangeBinding(el, {
    from, to, scrollStart, scrollEnd,
    apply: (wght) => {
      el.style.fontVariationSettings = `"wght" ${wght.toFixed(1)}`;
      el.style.fontWeight = String(Math.round(wght));
    },
  });
}

export function attachTrackingShift(el, { from = 0, to = -0.04, scrollStart = 0, scrollEnd = 400 } = {}) {
  if (!el) throw new Error('attachTrackingShift: element is required');
  el.classList.add('tws-tracking-shift');
  return attachRangeBinding(el, {
    from, to, scrollStart, scrollEnd,
    apply: (v) => { el.style.letterSpacing = `${v}em`; },
  });
}

function readNumberAttr(el, name, fallback) {
  const v = parseFloat(el.getAttribute(name));
  return Number.isFinite(v) ? v : fallback;
}

export function initTypographyMotion(root = document) {
  const reduced = prefersReduced();
  const handles = [];

  root.querySelectorAll('.tws-weight-shift').forEach((el) => {
    const from = readNumberAttr(el, 'data-weight-from', 200);
    const to   = readNumberAttr(el, 'data-weight-to', 700);
    if (reduced) {
      el.style.fontVariationSettings = `"wght" ${to}`;
      el.style.fontWeight = String(to);
      return;
    }
    // Use the element's top in the document as the natural scrollStart.
    const rect = el.getBoundingClientRect();
    const top = rect.top + window.scrollY;
    const scrollStart = Math.max(0, top - window.innerHeight);
    const scrollEnd   = top + rect.height * 0.5;
    handles.push(attachWeightShift(el, { from, to, scrollStart, scrollEnd }));
  });

  root.querySelectorAll('.tws-tracking-shift').forEach((el) => {
    const from = readNumberAttr(el, 'data-tracking-from', 0);
    const to   = readNumberAttr(el, 'data-tracking-to', -0.04);
    if (reduced) { el.style.letterSpacing = `${to}em`; return; }
    const rect = el.getBoundingClientRect();
    const top = rect.top + window.scrollY;
    const scrollStart = Math.max(0, top - window.innerHeight);
    const scrollEnd   = top + rect.height * 0.5;
    handles.push(attachTrackingShift(el, { from, to, scrollStart, scrollEnd }));
  });

  return {
    detach() { handles.forEach((h) => h.detach()); },
  };
}
