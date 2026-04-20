/* ==========================================================================
   Mockup B — Living architecture diagram
   Builds an SVG graph of 10 nodes + edges, pans the viewBox on scroll,
   renders detail panels, handles hover/tooltip/keyboard/tilt and Act V lenses.
   ========================================================================== */

const SVG_NS = 'http://www.w3.org/2000/svg';
const prefersReduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;

/* -------------------------------------------------------------------------
   Module metadata
   ------------------------------------------------------------------------- */
const NODES = [
  // top row — user entry
  { id: 'digichat',   x: 170,  y: 130, name: 'DigiChat',   tag: 'entry',
    accentVar: '--accent-digichat',
    blurb: 'Talk to your stack. Ship with your own keys.' },
  { id: 'digikey',    x: 400,  y: 200, name: 'DigiKey',    tag: 'identity',
    accentVar: '--accent-digikey',
    blurb: 'JWT + scoped API keys. RS256, JWKS.' },

  // center — orchestrator
  { id: 'digigraph',  x: 600,  y: 360, name: 'DigiGraph',  tag: 'supervisor', primary: true,
    accentVar: '--accent-digigraph',
    blurb: 'Route any request through the right specialist agent.' },

  // right fan — specialists
  { id: 'digiquant',  x: 880,  y: 240, name: 'DigiQuant',  tag: 'quant',
    accentVar: '--accent-digiquant',
    blurb: 'Backtest, optimize, and deploy trading strategies.' },
  { id: 'digisearch', x: 950,  y: 400, name: 'DigiSearch', tag: 'retrieval',
    accentVar: '--accent-digisearch',
    blurb: 'Find the right document. Ground any answer.' },
  { id: 'digilink',   x: 880,  y: 560, name: 'DigiLink',   tag: 'protocol',
    accentVar: '--accent-digilink',
    blurb: 'Protocol translation. Speak any API.' },

  // bottom fabric — infrastructure
  { id: 'digistore',  x: 250,  y: 560, name: 'DigiStore',  tag: 'storage',
    accentVar: '--accent-digistore',
    blurb: 'Storage abstraction. Postgres, S3, SQLite.' },
  { id: 'digismith',  x: 430,  y: 620, name: 'DigiSmith',  tag: 'observability',
    accentVar: '--accent-digismith',
    blurb: 'Tracing, metrics, /v1/status. Correlation-aware.' },
  { id: 'digiclaw',   x: 620,  y: 620, name: 'DigiClaw',   tag: 'runner',
    accentVar: '--accent-digiclaw',
    blurb: 'Heartbeat, audit, scheduled agent runs.' },
  { id: 'digibase',   x: 800,  y: 620, name: 'DigiBase',   tag: 'library',
    accentVar: '--accent-digibase',
    blurb: 'Shared Python primitives. HTTP, audit, redaction.' },
];

const EDGES = [
  // user flow
  ['digichat', 'digikey'],
  ['digikey',  'digigraph'],
  // graph routes to specialists
  ['digigraph', 'digiquant'],
  ['digigraph', 'digisearch'],
  ['digigraph', 'digilink'],
  // fabric wiring to orchestrator
  ['digigraph', 'digismith'],
  ['digigraph', 'digiclaw'],
  ['digigraph', 'digistore'],
  // specialists call out to fabric
  ['digiquant',  'digistore'],
  ['digisearch', 'digistore'],
  ['digilink',   'digibase'],
  ['digiquant',  'digibase'],
  ['digisearch', 'digibase'],
  // observability reach
  ['digiquant',  'digismith'],
  ['digisearch', 'digismith'],
];

/* Act → focus region + nodes in focus */
const ACT_CAMERAS = {
  hero:       { viewBox: [0,   0,   1200, 720], focus: [] },
  digigraph:  { viewBox: [360, 200, 560,  360], focus: ['digigraph', 'digichat', 'digikey'] },
  digiquant:  { viewBox: [600, 160, 560,  360], focus: ['digiquant', 'digigraph', 'digistore'] },
  digisearch: { viewBox: [620, 280, 560,  360], focus: ['digisearch', 'digigraph', 'digistore'] },
  digichat:   { viewBox: [40,  60,  620,  420], focus: ['digichat', 'digikey', 'digigraph'] },
  ecosystem:  { viewBox: [-80, -60, 1360, 840], focus: NODES.map(n => n.id) },
};

/* Detail panel content per act */
const ACT_DETAILS = {
  digigraph: {
    accent: 'digigraph',
    tag: 'Act I',
    title: 'DigiGraph',
    lede: 'Route any request through the right specialist agent.',
    body: 'A LangGraph supervisor composes sub-graphs and discovers tools through an MCP registry. Speak to it via an OpenAI-compatible API; it picks the right specialist, hands off, and stitches the result.',
    bullets: [
      'LangGraph supervisor + checkpointable sub-graphs',
      'MCP tool discovery against builtin and vertical registries',
      'Drop-in OpenAI-compatible /v1/chat/completions',
    ],
    schema: 'tree',
  },
  digiquant: {
    accent: 'digiquant',
    tag: 'Act II',
    title: 'DigiQuant',
    lede: 'Backtest, optimize, and deploy trading strategies.',
    body: 'NautilusTrader at the core. Atlas runs research cycles, Hermes handles live data feeds, Kairos schedules deliberation. Strategies register once and run everywhere — backtest, paper, live.',
    bullets: [
      'NautilusTrader engine; Polars for all data',
      'Atlas / Hermes / Kairos product family',
      'Human gate required before any live trade',
    ],
    schema: 'equity',
  },
  digisearch: {
    accent: 'digisearch',
    tag: 'Act III',
    title: 'DigiSearch',
    lede: 'Find the right document. Ground any answer.',
    body: 'Polars ingest, selective chunking, pluggable vector stores. Multi-mode retrieval blends dense, sparse, and structured filters. Chunks and queries expose as MCP tools for any agent.',
    bullets: [
      'Polars ingest → chunk → embed pipeline',
      'Pluggable vector store registry',
      'Dense + sparse + metadata hybrid retrieval',
    ],
    schema: 'chunks',
  },
  digichat: {
    accent: 'digichat',
    tag: 'Act IV',
    title: 'DigiChat',
    lede: 'Talk to your stack. Ship with your own keys.',
    body: 'Next.js + AI SDK BFF. Client-side BYOK through LiteLLM translation. Auth.js + Drizzle, row-level resource access via DigiKey-minted JWTs.',
    bullets: [
      'Next.js 15 + AI SDK streaming UI',
      'BYOK settings panel — keys never touch the server',
      'Adaptive UI driven by JWT scopes',
    ],
    schema: 'chat',
  },
  ecosystem: {
    accent: 'digigraph',
    tag: 'Act V',
    title: 'Plug it in.',
    lede: 'Every module ships three ways: container, Python library, MCP tool.',
    body: 'The same stack slots into your existing architecture, exposes itself as an MCP surface for other agents, and deploys to a laptop, a VM, or Kubernetes without code changes.',
    bullets: [
      'Plug into existing DB, auth, and apps',
      'Expose any module as MCP for other agents',
      'Run on laptop, VM, or Kubernetes — same image',
    ],
    schema: 'deploy',
  },
};

/* -------------------------------------------------------------------------
   DOM refs
   ------------------------------------------------------------------------- */
const svg        = document.getElementById('diagram');
const edgesLayer = document.getElementById('edges');
const nodesLayer = document.getElementById('nodes');
const extLayer   = document.getElementById('ext-nodes');
const mcpRing    = document.getElementById('mcp-ring');
const deployLayer= document.getElementById('deploy-layer');
const tooltip    = document.getElementById('tooltip');
const diagramWrap= document.getElementById('diagram-wrap');
const overlayCard= document.getElementById('overlay-card');
const detailPanel= document.getElementById('detail-panel');
const detailInner= document.getElementById('detail-inner');
const detailClose= document.getElementById('detail-close');
const lensControls = document.getElementById('lens-controls');

/* -------------------------------------------------------------------------
   Build nodes
   ------------------------------------------------------------------------- */
const nodeEls = {};

function el(name, attrs = {}, children = []) {
  const e = document.createElementNS(SVG_NS, name);
  for (const [k, v] of Object.entries(attrs)) {
    if (v != null) e.setAttribute(k, v);
  }
  for (const c of children) e.appendChild(c);
  return e;
}

function buildEdges() {
  for (const [fromId, toId] of EDGES) {
    const a = NODES.find(n => n.id === fromId);
    const b = NODES.find(n => n.id === toId);
    // Curved path via quadratic control midpoint nudge
    const mx = (a.x + b.x) / 2;
    const my = (a.y + b.y) / 2;
    // perpendicular nudge to avoid straight overlap
    const dx = b.x - a.x, dy = b.y - a.y;
    const len = Math.hypot(dx, dy) || 1;
    const nudge = 28;
    const cx = mx + (-dy / len) * nudge;
    const cy = my + (dx / len) * nudge;
    const d = `M ${a.x} ${a.y} Q ${cx} ${cy} ${b.x} ${b.y}`;
    const p = el('path', {
      d,
      'data-from': fromId,
      'data-to': toId,
    });
    // random dash offset so edges don't animate in lock-step
    p.style.animationDelay = `${-Math.random() * 6}s`;
    edgesLayer.appendChild(p);
  }
}

function buildNodes() {
  for (const node of NODES) {
    const g = el('g', {
      class: 'node',
      'data-id': node.id,
      tabindex: '0',
      role: 'button',
      'aria-label': `${node.name} — ${node.blurb}`,
      transform: `translate(${node.x}, ${node.y})`,
    });
    g.style.setProperty('--accent', `var(${node.accentVar})`);

    const r = node.primary ? 44 : 34;
    g.appendChild(el('circle', { class: 'halo', cx: 0, cy: 0, r: r + 14 }));
    g.appendChild(el('circle', { class: 'ring', cx: 0, cy: 0, r }));
    g.appendChild(el('circle', { class: 'dot',  cx: 0, cy: 0, r: 3 }));

    const label = el('text', { class: 'label', y: -r - 10 });
    label.textContent = node.name.toUpperCase();
    g.appendChild(label);

    const sub = el('text', { class: 'sublabel', y: r + 18 });
    sub.textContent = node.tag;
    g.appendChild(sub);

    // hover/click/keyboard handlers
    g.addEventListener('mouseenter', (e) => showTooltip(node, e));
    g.addEventListener('mousemove',  (e) => moveTooltip(e));
    g.addEventListener('mouseleave', () => hideTooltip());
    g.addEventListener('click',      () => openNodePanel(node));
    g.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' || e.key === ' ') {
        e.preventDefault();
        openNodePanel(node);
      }
    });

    nodesLayer.appendChild(g);
    nodeEls[node.id] = g;
  }
}

/* -------------------------------------------------------------------------
   Tooltip
   ------------------------------------------------------------------------- */
function showTooltip(node, ev) {
  tooltip.innerHTML = `<span class="t-name">${node.name}</span>${node.blurb}`;
  tooltip.style.setProperty('--accent', `var(${node.accentVar})`);
  tooltip.classList.add('is-visible');
  moveTooltip(ev);
}
function moveTooltip(ev) {
  const rect = diagramWrap.getBoundingClientRect();
  const x = ev.clientX - rect.left;
  const y = ev.clientY - rect.top;
  tooltip.style.left = `${x}px`;
  tooltip.style.top  = `${y - 12}px`;
}
function hideTooltip() {
  tooltip.classList.remove('is-visible');
}

/* -------------------------------------------------------------------------
   Detail panel
   ------------------------------------------------------------------------- */
function openNodePanel(node) {
  // map node id → act detail if available, else synthesize a mini panel
  const act = ACT_DETAILS[node.id];
  if (act) { openActPanel(node.id); return; }
  detailInner.innerHTML = `
    <span class="tag" style="--accent: var(${node.accentVar}); color: var(${node.accentVar}); border-color: var(${node.accentVar});">${node.tag}</span>
    <h3 style="color: var(${node.accentVar})">${node.name}</h3>
    <p class="lede">${node.blurb}</p>
  `;
  detailPanel.style.setProperty('--accent', `var(${node.accentVar})`);
  detailPanel.classList.add('is-open');
  detailPanel.setAttribute('aria-hidden', 'false');
  setActiveNode(node.id);
}

function openActPanel(actKey) {
  const a = ACT_DETAILS[actKey];
  if (!a) return;
  detailInner.innerHTML = `
    <span class="tag">${a.tag}</span>
    <h3>${a.title}</h3>
    <p class="lede">${a.lede}</p>
    ${renderMiniSchema(a.schema, a.accent)}
    <p class="body">${a.body}</p>
    <ul>${a.bullets.map(b => `<li>${b}</li>`).join('')}</ul>
  `;
  detailPanel.style.setProperty('--accent', `var(--accent-${a.accent})`);
  detailPanel.classList.add('is-open');
  detailPanel.setAttribute('aria-hidden', 'false');
  setActiveNode(actKey === 'ecosystem' ? null : actKey);
}

function closePanel() {
  detailPanel.classList.remove('is-open');
  detailPanel.setAttribute('aria-hidden', 'true');
  clearActive();
}

detailClose.addEventListener('click', closePanel);
document.addEventListener('keydown', (e) => {
  if (e.key === 'Escape') closePanel();
});

/* -------------------------------------------------------------------------
   Inline schematics inside the detail panel (tiny SVGs).
   ------------------------------------------------------------------------- */
function renderMiniSchema(kind, accent) {
  const accentVar = `var(--accent-${accent})`;
  if (kind === 'tree') {
    // Decision tree — supervisor branching to specialists
    return `<svg class="mini-schema" viewBox="0 0 300 130" aria-hidden="true">
      <g stroke="${accentVar}" stroke-width="1" fill="none" opacity="0.8">
        <path d="M150 20 L70 80" /><path d="M150 20 L150 80" /><path d="M150 20 L230 80" />
        <path d="M70 95 L40 115" /><path d="M70 95 L100 115" />
      </g>
      <g fill="${accentVar}">
        <circle cx="150" cy="20" r="5"/>
        <circle cx="70" cy="85" r="4"/><circle cx="150" cy="85" r="4"/><circle cx="230" cy="85" r="4"/>
        <circle cx="40" cy="118" r="3"/><circle cx="100" cy="118" r="3"/>
      </g>
    </svg>`;
  }
  if (kind === 'equity') {
    // Tiny equity curve
    return `<svg class="mini-schema" viewBox="0 0 300 130" aria-hidden="true">
      <path d="M10 100 L40 92 L65 96 L95 80 L120 82 L150 68 L180 72 L215 50 L250 55 L290 30"
            fill="none" stroke="${accentVar}" stroke-width="1.5"/>
      <line x1="10" y1="115" x2="290" y2="115" stroke="#333"/>
      <line x1="10" y1="10" x2="10" y2="115" stroke="#333"/>
    </svg>`;
  }
  if (kind === 'chunks') {
    // Document chunks + vectors
    let bars = '';
    for (let i = 0; i < 12; i++) {
      const x = 20 + i * 22;
      const h = 30 + Math.abs(Math.sin(i * 0.7)) * 50;
      bars += `<rect x="${x}" y="${110 - h}" width="12" height="${h}" fill="${accentVar}" opacity="${0.3 + (i % 3) * 0.2}"/>`;
    }
    return `<svg class="mini-schema" viewBox="0 0 300 130" aria-hidden="true">${bars}
      <line x1="10" y1="115" x2="290" y2="115" stroke="#333"/>
    </svg>`;
  }
  if (kind === 'chat') {
    // Chat bubbles
    return `<svg class="mini-schema" viewBox="0 0 300 130" aria-hidden="true">
      <rect x="20"  y="20"  width="140" height="26" rx="13" fill="none" stroke="#555" stroke-width="1"/>
      <rect x="140" y="55"  width="140" height="26" rx="13" fill="none" stroke="${accentVar}" stroke-width="1.2"/>
      <rect x="20"  y="90"  width="110" height="26" rx="13" fill="none" stroke="#555" stroke-width="1"/>
      <circle cx="270" cy="68" r="3" fill="${accentVar}"/>
    </svg>`;
  }
  if (kind === 'deploy') {
    return `<svg class="mini-schema" viewBox="0 0 300 130" aria-hidden="true">
      <g fill="none" stroke="${accentVar}" stroke-width="1.2">
        <rect x="25"  y="40" width="60" height="50" rx="4"/>
        <rect x="120" y="30" width="60" height="70" rx="4"/>
        <rect x="215" y="20" width="60" height="90" rx="4"/>
      </g>
      <g fill="${accentVar}" font-family="monospace" font-size="8" text-anchor="middle" letter-spacing="1.2">
        <text x="55"  y="110">LAPTOP</text>
        <text x="150" y="120">VM</text>
        <text x="245" y="125">K8S</text>
      </g>
    </svg>`;
  }
  return '';
}

/* -------------------------------------------------------------------------
   Active / focus state
   ------------------------------------------------------------------------- */
function setActiveNode(id) {
  for (const node of NODES) {
    const g = nodeEls[node.id];
    g.classList.toggle('is-active', node.id === id);
  }
  updateEdgeHighlights();
}
function clearActive() {
  for (const node of NODES) nodeEls[node.id].classList.remove('is-active');
  updateEdgeHighlights();
}

function applyFocusSet(ids) {
  const focusSet = new Set(ids);
  for (const node of NODES) {
    const g = nodeEls[node.id];
    if (focusSet.size === 0 || focusSet.size === NODES.length) {
      g.classList.remove('is-dim');
      g.classList.remove('is-focus');
    } else if (focusSet.has(node.id)) {
      g.classList.remove('is-dim');
      g.classList.add('is-focus');
    } else {
      g.classList.add('is-dim');
      g.classList.remove('is-focus');
    }
  }
  updateEdgeHighlights();
}

function updateEdgeHighlights() {
  const activeIds = NODES.filter(n => nodeEls[n.id].classList.contains('is-active') || nodeEls[n.id].classList.contains('is-focus')).map(n => n.id);
  const s = new Set(activeIds);
  edgesLayer.querySelectorAll('path').forEach(p => {
    const from = p.getAttribute('data-from');
    const to   = p.getAttribute('data-to');
    const hot = s.has(from) && s.has(to);
    p.classList.toggle('is-hot', hot);
    if (hot) {
      // pick the "leaf" (non-digigraph) node's accent for the edge color
      const leaf = from === 'digigraph' ? to : from;
      const leafNode = NODES.find(n => n.id === leaf);
      if (leafNode) p.style.setProperty('--edge-accent', `var(${leafNode.accentVar})`);
    } else {
      p.style.removeProperty('--edge-accent');
    }
  });
}

/* -------------------------------------------------------------------------
   Camera / viewBox tween
   ------------------------------------------------------------------------- */
let currentVB = [0, 0, 1200, 720];
let targetVB  = currentVB.slice();
let vbAnimStart = 0;
const VB_DURATION = 600;

function tweenViewBox(target) {
  if (prefersReduced) {
    currentVB = target.slice();
    svg.setAttribute('viewBox', currentVB.join(' '));
    return;
  }
  const from = currentVB.slice();
  vbAnimStart = performance.now();
  const dur = VB_DURATION;
  const ease = (t) => {
    // cubic-bezier(0.4, 0, 0.2, 1) approximation
    return t < 0.5 ? 2 * t * t : -1 + (4 - 2 * t) * t;
  };
  function step(now) {
    const t = Math.min(1, (now - vbAnimStart) / dur);
    const k = ease(t);
    currentVB = from.map((v, i) => v + (target[i] - v) * k);
    svg.setAttribute('viewBox', currentVB.join(' '));
    if (t < 1) requestAnimationFrame(step);
  }
  requestAnimationFrame(step);
  targetVB = target.slice();
}

/* -------------------------------------------------------------------------
   Scroll-driven act detection
   ------------------------------------------------------------------------- */
const actSections = Array.from(document.querySelectorAll('.act'));
let currentAct = null;

function detectAct() {
  const mid = window.innerHeight * 0.55;
  let active = null;
  for (const s of actSections) {
    const r = s.getBoundingClientRect();
    if (r.top <= mid && r.bottom > mid) { active = s; break; }
  }
  if (!active) active = actSections[0];
  actSections.forEach(s => s.classList.toggle('is-visible', s === active));

  const actKey = active.dataset.act;
  if (actKey === currentAct) return;
  currentAct = actKey;

  // fade hero overlay once user scrolls past hero
  overlayCard.classList.toggle('is-faded', actKey !== 'hero');

  // camera
  const cam = ACT_CAMERAS[actKey];
  if (cam) {
    tweenViewBox(cam.viewBox);
    applyFocusSet(cam.focus);
  }

  // panel
  if (actKey === 'hero') {
    closePanel();
  } else {
    openActPanel(actKey);
  }

  // lens controls
  lensControls.classList.toggle('is-visible', actKey === 'ecosystem');
  lensControls.setAttribute('aria-hidden', actKey === 'ecosystem' ? 'false' : 'true');
  if (actKey !== 'ecosystem') setLens(null);
}

window.addEventListener('scroll', detectAct, { passive: true });
window.addEventListener('resize', detectAct);

/* -------------------------------------------------------------------------
   Act V — lenses
   ------------------------------------------------------------------------- */
function buildExtNodes() {
  const exts = [
    { label: 'YOUR APP',  x: 80,   y: 320, target: 'digikey' },
    { label: 'YOUR DB',   x: 90,   y: 480, target: 'digistore' },
    { label: 'YOUR AUTH', x: 60,   y: 200, target: 'digikey' },
    { label: 'YOUR API',  x: 1120, y: 680, target: 'digilink' },
  ];
  for (const e of exts) {
    const tgt = NODES.find(n => n.id === e.target);
    const g = el('g', { class: 'ext' });
    g.appendChild(el('circle', { cx: e.x, cy: e.y, r: 26 }));
    const t = el('text', { x: e.x, y: e.y + 4 });
    t.textContent = e.label;
    g.appendChild(t);
    // dashed connector to the target node
    const d = `M ${e.x} ${e.y} L ${tgt.x} ${tgt.y}`;
    g.appendChild(el('path', { d }));
    extLayer.appendChild(g);
  }
}

function buildDeployGlyphs() {
  const glyphs = [
    { x: 220,  y: 360, w: 140, h: 90, label: 'LAPTOP' },
    { x: 530,  y: 340, w: 140, h: 110, label: 'VM' },
    { x: 840,  y: 320, w: 140, h: 130, label: 'KUBERNETES' },
  ];
  for (const gl of glyphs) {
    const g = el('g', { class: 'deploy' });
    g.appendChild(el('rect', { x: gl.x, y: gl.y, width: gl.w, height: gl.h, rx: 8 }));
    const t = el('text', { x: gl.x + gl.w / 2, y: gl.y + gl.h + 20 });
    t.textContent = gl.label;
    g.appendChild(t);
    deployLayer.appendChild(g);
  }
}

function setLens(lens) {
  extLayer.classList.toggle('is-visible', lens === 'plug');
  extLayer.setAttribute('aria-hidden', lens === 'plug' ? 'false' : 'true');

  mcpRing.classList.toggle('is-visible', lens === 'mcp');
  mcpRing.setAttribute('aria-hidden', lens === 'mcp' ? 'false' : 'true');

  deployLayer.classList.toggle('is-visible', lens === 'docker');
  deployLayer.setAttribute('aria-hidden', lens === 'docker' ? 'false' : 'true');

  // dim main nodes a touch when docker lens is active
  if (lens === 'docker') {
    NODES.forEach(n => nodeEls[n.id].classList.add('is-dim'));
  } else if (currentAct === 'ecosystem') {
    applyFocusSet(ACT_CAMERAS.ecosystem.focus);
  }

  for (const b of lensControls.querySelectorAll('.lens-btn')) {
    b.classList.toggle('is-active', b.dataset.lens === lens);
  }
}

lensControls.addEventListener('click', (e) => {
  const btn = e.target.closest('.lens-btn');
  if (!btn) return;
  setLens(btn.dataset.lens);
});

/* -------------------------------------------------------------------------
   Diagram tilt (mouse-follow, max ~2.5deg). Disabled under reduced motion
   and on touch.
   ------------------------------------------------------------------------- */
if (!prefersReduced && window.matchMedia('(hover: hover)').matches) {
  let tiltX = 0, tiltY = 0, targetX = 0, targetY = 0;
  diagramWrap.addEventListener('mousemove', (e) => {
    const r = diagramWrap.getBoundingClientRect();
    const px = (e.clientX - r.left) / r.width - 0.5;
    const py = (e.clientY - r.top)  / r.height - 0.5;
    targetY = px * 2.5;       // rotateY
    targetX = -py * 2.5;      // rotateX
  });
  diagramWrap.addEventListener('mouseleave', () => { targetX = 0; targetY = 0; });
  function tiltLoop() {
    tiltX += (targetX - tiltX) * 0.08;
    tiltY += (targetY - tiltY) * 0.08;
    svg.style.transform = `rotateX(${tiltX.toFixed(2)}deg) rotateY(${tiltY.toFixed(2)}deg)`;
    requestAnimationFrame(tiltLoop);
  }
  requestAnimationFrame(tiltLoop);
}

/* -------------------------------------------------------------------------
   Node entry stagger (on first paint)
   ------------------------------------------------------------------------- */
function staggerEntry() {
  if (prefersReduced) return;
  NODES.forEach((n, i) => {
    const g = nodeEls[n.id];
    const ring = g.querySelector('.ring');
    const halo = g.querySelector('.halo');
    const targetR = +ring.getAttribute('r');
    const targetH = +halo.getAttribute('r');
    ring.setAttribute('r', 0);
    halo.setAttribute('r', 0);
    const delay = 120 + i * 80;
    setTimeout(() => {
      ring.style.transition = 'r 300ms cubic-bezier(0.4,0,0.2,1)';
      halo.style.transition = 'r 400ms cubic-bezier(0.4,0,0.2,1)';
      ring.setAttribute('r', targetR);
      halo.setAttribute('r', targetH);
    }, delay);
  });
}

/* -------------------------------------------------------------------------
   Init
   ------------------------------------------------------------------------- */
buildEdges();
buildNodes();
buildExtNodes();
buildDeployGlyphs();
staggerEntry();
detectAct();
