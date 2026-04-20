/**
 * digithings.ai — sticky-stage scroll-jack orchestrator.
 *
 * The diagram fills a 100vh sticky stage; invisible scroll spacers drive
 * the active act. The overlay card holds all per-act slots, crossfading
 * in place as the user scrolls. No visible second column travels past.
 *
 * Responsibilities:
 *   - Mount living-architecture primitive inside the stage
 *   - Detect current act from scroll position and update overlay + camera
 *   - Click-to-scroll core nodes; click-to-panel for support nodes
 *   - Lazy-load terminal snippets when their slot first activates
 *   - Ecosystem Act V lens toggles + detail panel + typography motion
 */

import { initDiagram } from '../design-system/living-architecture/index.js';
import { initTerminal } from '../design-system/terminal/index.js';
import { initTypographyMotion } from '../design-system/typography-motion/index.js';

// ---------------------------------------------------------------------------
// Diagram data — 10 module nodes placed on the 1200x720 viewBox.
// Core modules form the spine left→right; support modules orbit above/below.
// ---------------------------------------------------------------------------
const NODES = [
    // Core (scroll acts)
    { id: 'digigraph',  label: 'DigiGraph',  x: 300, y: 360, group: 'core', accentVar: '--accent-digigraph' },
    { id: 'digiquant',  label: 'DigiQuant',  x: 540, y: 360, group: 'core', accentVar: '--accent-digiquant' },
    { id: 'digisearch', label: 'DigiSearch', x: 780, y: 360, group: 'core', accentVar: '--accent-digisearch' },
    { id: 'digichat',   label: 'DigiChat',   x: 1020, y: 360, group: 'core', accentVar: '--accent-digichat' },
    // Support (click-to-focus panels)
    { id: 'digikey',    label: 'DigiKey',    x: 180, y: 160, group: 'support', accentVar: '--accent-digikey' },
    { id: 'digismith',  label: 'DigiSmith',  x: 420, y: 560, group: 'support', accentVar: '--accent-digismith' },
    { id: 'digiclaw',   label: 'DigiClaw',   x: 660, y: 560, group: 'support', accentVar: '--accent-digiclaw' },
    { id: 'digibase',   label: 'DigiBase',   x: 900, y: 560, group: 'support', accentVar: '--accent-digibase' },
    { id: 'digistore',  label: 'DigiStore',  x: 1080, y: 160, group: 'support', accentVar: '--accent-digistore' },
    { id: 'digilink',   label: 'DigiLink',   x: 180, y: 560, group: 'support', accentVar: '--accent-digilink' },
];

const EDGES = [
    // core spine
    { source: 'digigraph',  target: 'digiquant' },
    { source: 'digiquant',  target: 'digisearch' },
    { source: 'digisearch', target: 'digichat' },
    // orchestrator wiring
    { source: 'digigraph',  target: 'digikey' },
    { source: 'digigraph',  target: 'digismith' },
    { source: 'digigraph',  target: 'digiclaw' },
    { source: 'digigraph',  target: 'digilink' },
    // cross-cuts
    { source: 'digiquant',  target: 'digistore' },
    { source: 'digisearch', target: 'digistore' },
    { source: 'digichat',   target: 'digikey' },
    { source: 'digismith',  target: 'digibase' },
    { source: 'digiclaw',   target: 'digibase' },
];

// Ordered sequence of acts (matches DOM spacer + slot order).
const ACT_ORDER = ['hero', 'digigraph', 'digiquant', 'digisearch', 'digichat', 'ecosystem'];

// ---------------------------------------------------------------------------
// Support-module detail panel content.
// ---------------------------------------------------------------------------
const SUPPORT = {
    digikey: {
        title: 'DigiKey',
        role: 'Auth + identity plane.',
        body: 'RS256 JWTs with a JWKS endpoint, scoped API keys, SSO federation, org + project membership, and row-level resource access baked straight into the issued tokens.',
        code: 'DIGIKEY_ISSUER=https://digikey.example.com',
        lang: 'sh',
    },
    digismith: {
        title: 'DigiSmith',
        role: 'Observability + redaction.',
        body: 'Correlation IDs propagate through every span; Prometheus /metrics is labeled by version and environment; PII is redacted before logs hit disk.',
        code: 'app.add_middleware(DigiSmithRequestIdMiddleware)',
        lang: 'py',
    },
    digiclaw: {
        title: 'DigiClaw',
        role: 'Always-on runtime + audit.',
        body: 'Heartbeat, immutable JSONL audit, and MCP skill surface for long-running autonomous work. Atlas runner scheduling and drift detection live here.',
        code: 'python -m digiclaw',
        lang: 'sh',
    },
    digibase: {
        title: 'DigiBase',
        role: 'Shared HTTP + audit primitives.',
        body: 'A deliberately minimal Python library — not a service. HTTP middleware, audit redaction, and error conventions so every other module behaves consistently.',
        code: 'from digibase.audit import redact_mapping',
        lang: 'py',
    },
    digistore: {
        title: 'DigiStore',
        role: 'One API over S3, MinIO, Postgres, SQLite.',
        body: 'A typed storage facade. Strategy artifacts, research outputs, and vector payloads travel the same path no matter where they land. Swap backends without touching business code.',
        code: 'store = DigiStore.configure(backend="s3", bucket="digi-artifacts")',
        lang: 'py',
    },
    digilink: {
        title: 'DigiLink',
        role: 'MCP protocol bridge.',
        body: 'When an external system speaks something DigiGraph does not — proprietary broker feeds, legacy REST surfaces, odd webhooks — DigiLink adapts it into MCP tool calls the orchestrator already understands.',
        code: 'digilink.register_adapter("legacy-rest", RestToMcpAdapter(...))',
        lang: 'py',
    },
};

// ---------------------------------------------------------------------------
// Terminal snippets — loaded on first activation of the owning slot.
// ---------------------------------------------------------------------------
async function loadSnippet(path, lang) {
    const res = await fetch(path);
    if (!res.ok) return [];
    const text = await res.text();
    return text.split('\n').map((raw) => {
        const trimmed = raw.trimStart();
        const isComment = trimmed.startsWith('#') || trimmed.startsWith('//');
        return {
            kind: isComment ? 'comment' : 'output',
            text: isComment ? trimmed.replace(/^(#|\/\/)\s?/, '') : raw,
            lang,
        };
    });
}

const HERO_LINES = [
    { kind: 'prompt', text: 'digithings ask "where does a request go?"' },
    { kind: 'output', text: '→ digigraph routes to digisearch + digiquant' },
    { kind: 'comment', text: 'BYOK, loopback, audit on by default' },
];

const TERMINAL_MAP = {
    digigraph:  { elementId: 'term-digigraph',  path: 'snippets/digigraph.py.txt',  lang: 'py' },
    digiquant:  { elementId: 'term-digiquant',  path: 'snippets/digiquant.py.txt',  lang: 'py' },
    digisearch: { elementId: 'term-digisearch', path: 'snippets/digisearch.py.txt', lang: 'py' },
    digichat:   { elementId: 'term-digichat',   path: 'snippets/digichat.ts.txt',   lang: 'ts' },
};
const terminalsStarted = new Set();

async function ensureTerminalFor(actId) {
    const spec = TERMINAL_MAP[actId];
    if (!spec || terminalsStarted.has(actId)) return;
    const host = document.getElementById(spec.elementId);
    if (!host) return;
    terminalsStarted.add(actId);
    const lines = await loadSnippet(spec.path, spec.lang);
    initTerminal({ elementId: spec.elementId, lines, speed: 'fast' });
}

// ---------------------------------------------------------------------------
// Detail panel — opens for support-node clicks, does not change scroll.
// ---------------------------------------------------------------------------
function openDetailPanel(id) {
    const panel = document.getElementById('detail-panel');
    const spec = SUPPORT[id];
    if (!panel || !spec) return;
    document.getElementById('detail-title').textContent = spec.title;
    document.getElementById('detail-role').textContent = spec.role;
    document.getElementById('detail-body').textContent = spec.body;
    document.getElementById('detail-code').textContent = spec.code;
    panel.classList.add('is-open');
    panel.setAttribute('aria-hidden', 'false');
    panel.dataset.module = id;
}

function closeDetailPanel() {
    const panel = document.getElementById('detail-panel');
    if (!panel) return;
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
}

// ---------------------------------------------------------------------------
// Ecosystem lens toggles (visible only during Act V).
// ---------------------------------------------------------------------------
const LENS_CAPTIONS = {
    plugin: 'Plug your app, DB, and auth into DigiGraph, DigiStore, and DigiKey.',
    mcp:    'Every module exposes its capabilities as MCP tool calls.',
    docker: 'One compose file — runs on laptop, VM, or Kubernetes.',
};

function setLens(lens) {
    const overlaysSvg = document.getElementById('arch-overlays');
    if (!overlaysSvg) return;
    overlaysSvg.classList.toggle('is-plugin', lens === 'plugin');
    overlaysSvg.classList.toggle('is-mcp', lens === 'mcp');
    overlaysSvg.classList.toggle('is-docker', lens === 'docker');
    overlaysSvg.setAttribute('aria-hidden', lens ? 'false' : 'true');
    for (const btn of document.querySelectorAll('.eco-toggle')) {
        const on = btn.dataset.lens === lens;
        btn.classList.toggle('is-active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    const caption = document.getElementById('eco-caption');
    if (caption) caption.textContent = lens ? LENS_CAPTIONS[lens] : 'Pick a lens above.';
}

const resetLens = () => setLens(null);

function initEcosystemToggles() {
    for (const btn of document.querySelectorAll('.eco-toggle')) {
        btn.addEventListener('click', () => {
            const already = btn.classList.contains('is-active');
            setLens(already ? null : btn.dataset.lens);
        });
    }
}

// ---------------------------------------------------------------------------
// Scroll-jack orchestration: map scrollY to the active act.
// ---------------------------------------------------------------------------
const spacers = Array.from(document.querySelectorAll('.dt-spacer'));
const slots = Array.from(document.querySelectorAll('.dt-act-slot'));

function currentActFromScroll() {
    // Probe at mid-viewport — whichever spacer contains that probe wins.
    const probeY = window.scrollY + window.innerHeight * 0.5;
    let active = ACT_ORDER[0];
    for (const spacer of spacers) {
        const top = spacer.offsetTop;
        if (top <= probeY) active = spacer.dataset.act;
    }
    return active;
}

function scrollToAct(actId) {
    const spacer = spacers.find((s) => s.dataset.act === actId);
    if (!spacer) return;
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({
        top: spacer.offsetTop + 2,
        behavior: reduced ? 'auto' : 'smooth',
    });
}

let currentAct = null;

function applyAct(diagram, actId) {
    if (actId === currentAct) return;
    currentAct = actId;

    // Crossfade slots in the overlay card.
    for (const slot of slots) {
        slot.classList.toggle('is-active', slot.dataset.slot === actId);
    }

    // Diagram camera.
    if (actId === 'hero' || actId === 'ecosystem') {
        if (typeof diagram.reset === 'function') diagram.reset();
    } else {
        if (typeof diagram.focus === 'function') diagram.focus(actId);
    }

    // Lens controls reset when leaving the ecosystem act.
    if (actId !== 'ecosystem') resetLens();

    // Lazy-load the terminal widget the first time its slot goes active.
    ensureTerminalFor(actId);

    // Keep URL hash in sync for deep-linking, but not during hero.
    if (actId !== 'hero' && history && history.replaceState) {
        history.replaceState(null, '', `#${actId}`);
    }
}

// ---------------------------------------------------------------------------
// Boot.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', () => {
    const diagram = initDiagram({
        hostId: 'arch-host',
        svgId: 'arch-svg',
        nodes: NODES,
        edges: EDGES,
        onNodeFocus: (id) => {
            const node = NODES.find((n) => n.id === id);
            if (!node) return;
            if (node.group === 'support') {
                // Support node → panel only. Scroll unchanged.
                openDetailPanel(id);
            } else {
                // Core node → scroll to its act spacer. applyAct fires from scroll.
                closeDetailPanel();
                scrollToAct(id);
            }
        },
    });

    // Hero terminal — small, placeholder-only, mount immediately.
    initTerminal({ elementId: 'hero-term', lines: HERO_LINES, speed: 'slow' });

    // Detail-panel close wiring.
    const closeBtn = document.querySelector('.dt-detail-close');
    if (closeBtn) closeBtn.addEventListener('click', closeDetailPanel);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetailPanel();
    });

    // Nav + hero CTA clicks route through scrollToAct so camera stays in sync.
    document.querySelectorAll('[data-nav-act]').forEach((a) => {
        a.addEventListener('click', (e) => {
            const target = a.getAttribute('data-nav-act');
            if (!target) return;
            e.preventDefault();
            scrollToAct(target);
        });
    });

    initEcosystemToggles();
    initTypographyMotion();

    // Scroll-jack loop — rAF-throttled.
    let ticking = false;
    const onScroll = () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            const next = currentActFromScroll();
            applyAct(diagram, next);
            ticking = false;
        });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);

    // Initial paint — set the hero state.
    applyAct(diagram, currentActFromScroll());

    // Deep-link support: if URL already has a module hash, scroll to that act.
    const hash = window.location.hash.replace('#', '');
    if (hash && ACT_ORDER.includes(hash)) {
        setTimeout(() => scrollToAct(hash), 200);
    } else if (hash && NODES.some((n) => n.id === hash)) {
        const node = NODES.find((n) => n.id === hash);
        setTimeout(() => {
            if (node.group === 'support') openDetailPanel(hash);
        }, 300);
    }
});
