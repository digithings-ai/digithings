/**
 * digithings.ai — sticky-stage scroll-jack orchestrator (Mockup B pattern).
 *
 *   • The diagram fills a 100vh sticky stage; hero-card (top-left) visible
 *     only during hero; detail-panel slides in from the right per act.
 *   • Scroll-track below the stage contains visible .dt-act sections; only
 *     the current act's .dt-act-anchor pill is opaque, giving scroll a
 *     subtle visible event without a big central card competing with the
 *     diagram for the user's attention.
 *   • Act detection uses getBoundingClientRect on .dt-act sections
 *     (matches Mockup B exactly).
 */

import { initDiagram } from '../design-system/living-architecture/index.js';
import { initTerminal } from '../design-system/terminal/index.js';
import { initTypographyMotion } from '../design-system/typography-motion/index.js';

// ---------------------------------------------------------------------------
// Diagram data — 10 module nodes placed on the 1200x720 viewBox.
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
    { source: 'digigraph',  target: 'digiquant' },
    { source: 'digiquant',  target: 'digisearch' },
    { source: 'digisearch', target: 'digichat' },
    { source: 'digigraph',  target: 'digikey' },
    { source: 'digigraph',  target: 'digismith' },
    { source: 'digigraph',  target: 'digiclaw' },
    { source: 'digigraph',  target: 'digilink' },
    { source: 'digiquant',  target: 'digistore' },
    { source: 'digisearch', target: 'digistore' },
    { source: 'digichat',   target: 'digikey' },
    { source: 'digismith',  target: 'digibase' },
    { source: 'digiclaw',   target: 'digibase' },
];

// ---------------------------------------------------------------------------
// Support-module detail panel content.
// ---------------------------------------------------------------------------
const SUPPORT = {
    digikey: {
        title: 'DigiKey', kicker: 'Support · Auth',
        role: 'Auth + identity plane.',
        body: 'RS256 JWTs with a JWKS endpoint, scoped API keys, SSO federation, org + project membership, and row-level resource access baked straight into the issued tokens.',
        code: 'DIGIKEY_ISSUER=https://digikey.example.com',
    },
    digismith: {
        title: 'DigiSmith', kicker: 'Support · Observability',
        role: 'Observability + redaction.',
        body: 'Correlation IDs propagate through every span; Prometheus /metrics is labeled by version and environment; PII is redacted before logs hit disk.',
        code: 'app.add_middleware(DigiSmithRequestIdMiddleware)',
    },
    digiclaw: {
        title: 'DigiClaw', kicker: 'Support · Runtime',
        role: 'Always-on runtime + audit.',
        body: 'Heartbeat, immutable JSONL audit, and MCP skill surface for long-running autonomous work. Atlas runner scheduling and drift detection live here.',
        code: 'python -m digiclaw',
    },
    digibase: {
        title: 'DigiBase', kicker: 'Support · Library',
        role: 'Shared HTTP + audit primitives.',
        body: 'A deliberately minimal Python library — not a service. HTTP middleware, audit redaction, and error conventions so every other module behaves consistently.',
        code: 'from digibase.audit import redact_mapping',
    },
    digistore: {
        title: 'DigiStore', kicker: 'Support · Storage',
        role: 'One API over S3, MinIO, Postgres, SQLite.',
        body: 'A typed storage facade. Strategy artifacts, research outputs, and vector payloads travel the same path no matter where they land. Swap backends without touching business code.',
        code: 'store = DigiStore.configure(backend="s3", bucket="digi-artifacts")',
    },
    digilink: {
        title: 'DigiLink', kicker: 'Support · Protocol',
        role: 'MCP protocol bridge.',
        body: 'When an external system speaks something DigiGraph does not — proprietary broker feeds, legacy REST surfaces, odd webhooks — DigiLink adapts it into MCP tool calls.',
        code: 'digilink.register_adapter("legacy-rest", RestToMcpAdapter(...))',
    },
};

// ---------------------------------------------------------------------------
// Terminal snippets — lazy-loaded on first activation of a core act.
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
// Ecosystem lens toggles.
// ---------------------------------------------------------------------------
const LENS_CAPTIONS = {
    plugin: 'Plug your app, DB, and auth into DigiGraph, DigiStore, and DigiKey.',
    mcp:    'Every module exposes its capabilities as MCP tool calls.',
    docker: 'One compose file — runs on laptop, VM, or Kubernetes.',
};

function setLens(lens) {
    const overlays = document.getElementById('arch-overlays');
    if (!overlays) return;
    overlays.classList.toggle('is-plugin', lens === 'plugin');
    overlays.classList.toggle('is-mcp', lens === 'mcp');
    overlays.classList.toggle('is-docker', lens === 'docker');
    overlays.setAttribute('aria-hidden', lens ? 'false' : 'true');
    for (const btn of document.querySelectorAll('.eco-toggle, .dt-lens-btn')) {
        const on = btn.dataset.lens === lens;
        btn.classList.toggle('is-active', on);
        btn.setAttribute('aria-selected', on ? 'true' : 'false');
    }
    const caption = document.getElementById('eco-caption');
    if (caption) caption.textContent = lens ? LENS_CAPTIONS[lens] : 'Each lens overlays the diagram.';
}

function initLensControls() {
    for (const btn of document.querySelectorAll('.eco-toggle, .dt-lens-btn')) {
        btn.addEventListener('click', () => {
            const already = btn.classList.contains('is-active');
            setLens(already ? null : btn.dataset.lens);
        });
    }
}

// ---------------------------------------------------------------------------
// Detail-panel + hero-card + act-pill orchestration.
// ---------------------------------------------------------------------------
const detailPanel = () => document.getElementById('detail-panel');
const heroCard = () => document.getElementById('hero-card');
const lensControls = () => document.getElementById('lens-controls');
const actSections = () => Array.from(document.querySelectorAll('.dt-act'));
const detailSlots = () => Array.from(document.querySelectorAll('.dt-detail-slot'));

function activateDetailSlot(slotName, accent) {
    const panel = detailPanel();
    if (!panel) return;
    for (const slot of detailSlots()) {
        slot.classList.toggle('is-active', slot.dataset.slot === slotName);
    }
    if (accent) panel.dataset.accent = accent;
    else delete panel.dataset.accent;
}

function openDetailPanel() {
    const panel = detailPanel();
    if (!panel) return;
    panel.classList.add('is-open');
    panel.setAttribute('aria-hidden', 'false');
}

function closeDetailPanel() {
    const panel = detailPanel();
    if (!panel) return;
    panel.classList.remove('is-open');
    panel.setAttribute('aria-hidden', 'true');
    delete panel.dataset.module;
}

function openSupportPanel(id) {
    const spec = SUPPORT[id];
    if (!spec) return;
    const slot = document.getElementById('detail-support');
    if (!slot) return;
    document.getElementById('support-title').textContent = spec.title;
    document.getElementById('support-kicker').textContent = spec.kicker;
    document.getElementById('support-role').textContent = spec.role;
    document.getElementById('support-body').textContent = spec.body;
    document.getElementById('support-code').textContent = spec.code;
    activateDetailSlot('support', null);
    openDetailPanel();
    detailPanel().dataset.module = id;
}

// ---------------------------------------------------------------------------
// Scroll-jack — Mockup B pattern: probe mid-viewport against .dt-act rects.
// ---------------------------------------------------------------------------
const ACT_ORDER = ['digigraph', 'digiquant', 'digisearch', 'digichat', 'ecosystem'];

function currentActFromScroll() {
    const probeY = window.innerHeight * 0.55;
    const acts = actSections();
    for (const a of acts) {
        const r = a.getBoundingClientRect();
        if (r.top <= probeY && r.bottom > probeY) return a.dataset.act;
    }
    // Above the first act → hero (stage-only initial view).
    if (acts.length && acts[0].getBoundingClientRect().top > probeY) return 'hero';
    // Past the last act → keep the last (ecosystem) active.
    return acts.length ? acts[acts.length - 1].dataset.act : 'hero';
}

function scrollToAct(actId) {
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    if (actId === 'hero') {
        window.scrollTo({ top: 0, behavior: reduced ? 'auto' : 'smooth' });
        return;
    }
    const section = actSections().find((a) => a.dataset.act === actId);
    if (!section) return;
    section.scrollIntoView({ behavior: reduced ? 'auto' : 'smooth', block: 'start' });
}

let currentAct = null;

function applyAct(diagram, actId) {
    if (actId === currentAct) return;
    currentAct = actId;

    // Toggle current .dt-act's pill visibility.
    for (const a of actSections()) {
        a.classList.toggle('is-visible', a.dataset.act === actId);
    }

    // Hero-card fade (only visible at the very top).
    heroCard()?.classList.toggle('is-faded', actId !== 'hero');

    // Diagram camera.
    if (actId === 'hero' || actId === 'ecosystem') {
        if (typeof diagram.reset === 'function') diagram.reset();
    } else if (typeof diagram.focus === 'function') {
        diagram.focus(actId);
    }

    // Detail panel contents follow the current act, open on non-hero.
    if (actId === 'hero') {
        closeDetailPanel();
        setLens(null);
    } else {
        const accentMap = {
            digigraph: 'digigraph',
            digiquant: 'digiquant',
            digisearch: 'digisearch',
            digichat: 'digichat',
            ecosystem: null,
        };
        activateDetailSlot(actId, accentMap[actId] ?? null);
        openDetailPanel();
    }

    // Lens controls live inside the stage; visible only on ecosystem.
    lensControls()?.classList.toggle('is-visible', actId === 'ecosystem');
    lensControls()?.setAttribute('aria-hidden', actId === 'ecosystem' ? 'false' : 'true');
    if (actId !== 'ecosystem') setLens(null);

    // Lazy-load terminal on first core-act activation.
    ensureTerminalFor(actId);

    // Hash sync (off for hero).
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
                openSupportPanel(id);
            } else {
                scrollToAct(id);
            }
        },
    });

    // Hero terminal mounts immediately (always visible during hero).
    initTerminal({ elementId: 'hero-term', lines: HERO_LINES, speed: 'slow' });

    // Wire the detail-panel close button.
    document.getElementById('detail-close')?.addEventListener('click', () => {
        // If panel holds a support module, close; else snap back to hero.
        if (detailPanel().dataset.module) {
            closeDetailPanel();
            // Return to the current act's own slot so next scroll change is smooth.
            if (currentAct && currentAct !== 'hero') {
                applyAct(diagram, currentAct);
            }
        } else {
            scrollToAct('hero');
        }
    });

    // Esc closes the panel / resets camera.
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') {
            if (detailPanel().dataset.module) {
                closeDetailPanel();
                if (currentAct && currentAct !== 'hero') applyAct(diagram, currentAct);
            } else {
                scrollToAct('hero');
                setLens(null);
            }
        }
    });

    // Nav + hero CTA click → scrollToAct, not native anchor (keeps camera in sync).
    for (const link of document.querySelectorAll('[data-nav-act]')) {
        link.addEventListener('click', (e) => {
            const actId = link.dataset.navAct;
            if (!actId) return;
            e.preventDefault();
            scrollToAct(actId);
        });
    }

    initLensControls();
    initTypographyMotion();

    // Scroll listener updates the active act.
    let ticking = false;
    const onScroll = () => {
        if (ticking) return;
        ticking = true;
        requestAnimationFrame(() => {
            ticking = false;
            const next = currentActFromScroll();
            applyAct(diagram, next);
        });
    };
    window.addEventListener('scroll', onScroll, { passive: true });
    window.addEventListener('resize', onScroll);

    // Initial paint.
    applyAct(diagram, currentActFromScroll());

    // Deep-link: if URL has #digigraph etc. on load, scroll to it.
    if (location.hash && ACT_ORDER.includes(location.hash.slice(1))) {
        setTimeout(() => scrollToAct(location.hash.slice(1)), 50);
    }
});
