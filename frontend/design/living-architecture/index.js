/* ==========================================================================
   @digithings/design — living-architecture
   --------------------------------------------------------------------------
   Reusable interactive SVG diagram engine. Extracted from the Mockup B
   landing exploration, slimmed to a primitive with a small API. Act-driven
   scroll logic, detail panels, tooltips, and lens controls are NOT part of
   this module — those belong to the consuming page.

   Usage:
     import { initDiagram } from '@digithings/design/living-architecture';
     import '@digithings/design/living-architecture/styles.css';

     const { camera, focus, reset, destroy } = initDiagram({
       hostId: 'arch-host',
       svgId:  'arch-svg',
       nodes:  [ { id, label, x, y, accentVar, group? } ],
       edges:  [ { source, target } ],
       onNodeFocus: (id) => { ... },
     });
   ========================================================================== */

const SVG_NS = 'http://www.w3.org/2000/svg';
const DEFAULT_VIEWBOX = [0, 0, 1200, 720];
const TWEEN_DURATION = 600;

function el(name, attrs = {}, children = []) {
  const e = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v != null) e.setAttribute(k, v);
  }
  for (const c of children) e.appendChild(c);
  return e;
}

// cubic-bezier(0.4, 0, 0.2, 1) approximation
function easeStandard(t) {
  return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
}

export function initDiagram({ hostId, svgId, nodes, edges, onNodeFocus }) {
  if (!svgId || !Array.isArray(nodes) || !Array.isArray(edges)) {
    throw new Error('initDiagram: svgId, nodes, edges are required');
  }

  const prefersReduced = typeof window !== 'undefined'
    && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  const svg = document.getElementById(svgId);
  if (!svg) throw new Error(`initDiagram: no SVG with id "${svgId}"`);
  const host = hostId ? document.getElementById(hostId) : svg.parentElement;
  if (!host) throw new Error(`initDiagram: no host element for "${hostId}"`);

  // Ensure host is positionable so we can anchor the zoom-out button.
  if (getComputedStyle(host).position === 'static') {
    host.style.position = 'relative';
  }
  host.classList.add('la-host');
  if (prefersReduced) host.classList.add('la-reduced-motion');
  if (!host.hasAttribute('tabindex')) host.setAttribute('tabindex', '0');

  // Compute viewBox from the attribute on the SVG (or default).
  const initialVB = (svg.getAttribute('viewBox') || DEFAULT_VIEWBOX.join(' '))
    .split(/\s+/).map(Number);
  if (initialVB.length !== 4 || initialVB.some(Number.isNaN)) {
    initialVB.splice(0, initialVB.length, ...DEFAULT_VIEWBOX);
  }

  svg.classList.add('la-svg');
  // Clear any prior children (idempotent re-init).
  while (svg.firstChild) svg.removeChild(svg.firstChild);

  const edgesLayer = el('g', { class: 'la-edges' });
  const nodesLayer = el('g', { class: 'la-nodes' });
  svg.appendChild(edgesLayer);
  svg.appendChild(nodesLayer);

  const nodeEls = Object.create(null);
  const coreNodes = nodes.filter((n) => n.group === 'core');

  // --------------------------------------------------------------------
  // Edges
  // --------------------------------------------------------------------
  for (const edge of edges) {
    const a = nodes.find((n) => n.id === edge.source);
    const b = nodes.find((n) => n.id === edge.target);
    if (!a || !b) continue;
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const nudge = 28;
    const cx = mx + (-dy / len) * nudge;
    const cy = my + (dx / len) * nudge;
    const d = `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
    const p = el('path', {
      class: 'la-edge',
      d,
      'data-from': a.id,
      'data-to': b.id,
    });
    // Stagger the dashoffset cycle so edges don't animate in lock-step.
    p.style.animationDelay = `${-Math.random() * 6}s`;
    edgesLayer.appendChild(p);
  }

  // --------------------------------------------------------------------
  // Nodes
  // --------------------------------------------------------------------
  for (const node of nodes) {
    const g = el('g', {
      class: 'la-node',
      'data-id': node.id,
      tabindex: '0',
      role: 'button',
      'aria-label': node.label || node.id,
      transform: `translate(${node.x}, ${node.y})`,
    });
    if (node.accentVar) {
      g.style.setProperty('--accent', `var(${node.accentVar})`);
    }
    const r = node.group === 'core' ? 44 : 34;
    g.appendChild(el('circle', { class: 'la-halo', cx: 0, cy: 0, r: r + 14 }));
    g.appendChild(el('circle', { class: 'la-ring', cx: 0, cy: 0, r }));
    g.appendChild(el('circle', { class: 'la-dot', cx: 0, cy: 0, r: 3 }));
    const label = el('text', { class: 'la-label', y: -r - 10 });
    label.textContent = (node.label || node.id).toUpperCase();
    g.appendChild(label);

    g.addEventListener('click', () => activate(node.id));
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        activate(node.id);
      }
    });

    nodesLayer.appendChild(g);
    nodeEls[node.id] = g;
  }

  // --------------------------------------------------------------------
  // Camera / viewBox tween
  // --------------------------------------------------------------------
  let currentVB = initialVB.slice();
  let rafId = 0;

  function applyViewBox(vb) {
    svg.setAttribute('viewBox', vb.join(' '));
  }
  applyViewBox(currentVB);

  function tweenTo(target) {
    if (prefersReduced) {
      currentVB = target.slice();
      applyViewBox(currentVB);
      return;
    }
    const from = currentVB.slice();
    const start = performance.now();
    if (rafId) cancelAnimationFrame(rafId);
    function step(now) {
      const t = Math.min(1, (now - start) / TWEEN_DURATION);
      const k = easeStandard(t);
      currentVB = from.map((v, i) => v + (target[i] - v) * k);
      applyViewBox(currentVB);
      if (t < 1) rafId = requestAnimationFrame(step);
      else rafId = 0;
    }
    rafId = requestAnimationFrame(step);
  }

  function nodeBBox(node, pad = 180) {
    return [node.x - pad, node.y - pad, pad * 2, pad * 2];
  }

  const camera = {
    focus(id) {
      const node = nodes.find((n) => n.id === id);
      if (!node) return;
      tweenTo(nodeBBox(node));
    },
    reset() {
      tweenTo(initialVB.slice());
    },
    zoomTo(bbox) {
      if (!Array.isArray(bbox) || bbox.length !== 4) return;
      tweenTo(bbox.slice());
    },
  };

  // --------------------------------------------------------------------
  // Focus / bloom state
  // --------------------------------------------------------------------
  let activeId = null;

  function setActive(id) {
    activeId = id;
    for (const n of nodes) {
      const g = nodeEls[n.id];
      g.classList.toggle('la-is-active', n.id === id);
      g.classList.toggle('la-is-dim', id != null && n.id !== id);
    }
  }

  function clearActive() {
    activeId = null;
    for (const n of nodes) {
      const g = nodeEls[n.id];
      g.classList.remove('la-is-active', 'la-is-dim');
    }
  }

  function activate(id) {
    setActive(id);
    camera.focus(id);
    if (typeof onNodeFocus === 'function') {
      try { onNodeFocus(id); } catch (_) { /* swallow */ }
    }
  }

  function focus(id) { activate(id); }
  function reset() {
    clearActive();
    camera.reset();
  }

  // --------------------------------------------------------------------
  // Zoom-out button (top-right of host)
  // --------------------------------------------------------------------
  const zoomBtn = document.createElement('button');
  zoomBtn.type = 'button';
  zoomBtn.className = 'la-zoom-out-btn';
  zoomBtn.setAttribute('aria-label', 'Zoom out');
  zoomBtn.textContent = '\u2922'; // ⤢ — diagonal arrows glyph
  zoomBtn.addEventListener('click', () => reset());
  host.appendChild(zoomBtn);

  // --------------------------------------------------------------------
  // Keyboard navigation on host
  // --------------------------------------------------------------------
  function cycleCore(delta) {
    if (coreNodes.length === 0) return;
    const idx = coreNodes.findIndex((n) => n.id === activeId);
    const next = coreNodes[((idx === -1 ? 0 : idx + delta) + coreNodes.length) % coreNodes.length];
    activate(next.id);
  }

  function onKey(e) {
    // Only intercept when focus is inside the host.
    if (!host.contains(document.activeElement) && document.activeElement !== host) return;
    switch (e.key) {
      case 'ArrowLeft':
        e.preventDefault(); cycleCore(-1); break;
      case 'ArrowRight':
        e.preventDefault(); cycleCore(1); break;
      case 'ArrowUp':
        e.preventDefault(); reset(); break;
      case 'ArrowDown':
        e.preventDefault();
        if (activeId && coreNodes.some((n) => n.id === activeId)) activate(activeId);
        else if (coreNodes[0]) activate(coreNodes[0].id);
        break;
      case 'Escape':
        e.preventDefault(); reset(); break;
      default: break;
      // Enter is handled on the focused node element; Tab is native.
    }
  }
  host.addEventListener('keydown', onKey);

  function destroy() {
    host.removeEventListener('keydown', onKey);
    if (rafId) cancelAnimationFrame(rafId);
    zoomBtn.remove();
    while (svg.firstChild) svg.removeChild(svg.firstChild);
    host.classList.remove('la-host', 'la-reduced-motion');
  }

  return { camera, focus, reset, destroy };
}
