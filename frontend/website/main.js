/**
 * digithings.ai — architecture-editorial landing page orchestrator.
 *
 * Wires the living-architecture diagram, typography motion, and per-module
 * terminal widgets. Handles support-node click → detail panel, and the
 * Act V ecosystem lens toggles (plug-in / MCP / Docker overlays).
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

// ---------------------------------------------------------------------------
// Support-module detail panel content (source: AGENTS.md / ARCHITECTURE.md).
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
// Terminal snippets: load the real-code text fragments, wrap into terminal
// line objects (kind=comment for #/// lines, kind=output for code lines).
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

// ---------------------------------------------------------------------------
// Detail panel — open/close with a support-node focus.
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
// Ecosystem lens toggles.
// ---------------------------------------------------------------------------
function initEcosystemToggles() {
    const overlaysSvg = document.getElementById('arch-overlays');
    const buttons = Array.from(document.querySelectorAll('.eco-toggle'));
    const caption = document.getElementById('eco-caption');
    if (!overlaysSvg || buttons.length === 0) return;

    const CAPTIONS = {
        plugin: 'Plug your app, DB, and auth into DigiGraph, DigiStore, and DigiKey.',
        mcp:    'Every module exposes its capabilities as MCP tool calls.',
        docker: 'One compose file — runs on laptop, VM, or Kubernetes.',
    };

    function setLens(lens) {
        overlaysSvg.classList.toggle('is-plugin', lens === 'plugin');
        overlaysSvg.classList.toggle('is-mcp', lens === 'mcp');
        overlaysSvg.classList.toggle('is-docker', lens === 'docker');
        overlaysSvg.setAttribute('aria-hidden', lens ? 'false' : 'true');
        for (const btn of buttons) {
            const on = btn.dataset.lens === lens;
            btn.classList.toggle('is-active', on);
            btn.setAttribute('aria-selected', on ? 'true' : 'false');
        }
        if (caption) caption.textContent = lens ? CAPTIONS[lens] : 'Pick a lens above.';
    }

    for (const btn of buttons) {
        btn.addEventListener('click', () => {
            const lens = btn.dataset.lens;
            const already = btn.classList.contains('is-active');
            setLens(already ? null : lens);
        });
    }
}

// ---------------------------------------------------------------------------
// Scroll-driven camera focus: when a core act comes into view, focus the
// diagram on that module. Support-node focus is click-driven only.
// ---------------------------------------------------------------------------
function initScrollActs(diagram) {
    const acts = document.querySelectorAll('.act-core[data-act]');
    if (acts.length === 0) return;

    const observer = new IntersectionObserver((entries) => {
        for (const entry of entries) {
            if (entry.isIntersecting && entry.intersectionRatio > 0.4) {
                const id = entry.target.dataset.act;
                if (id) diagram.focus(id);
            }
        }
    }, { threshold: [0.4, 0.6] });

    for (const a of acts) observer.observe(a);
}

// ---------------------------------------------------------------------------
// Boot.
// ---------------------------------------------------------------------------
document.addEventListener('DOMContentLoaded', async () => {
    const diagram = initDiagram({
        hostId: 'arch-host',
        svgId: 'arch-svg',
        nodes: NODES,
        edges: EDGES,
        onNodeFocus: (id) => {
            const node = NODES.find((n) => n.id === id);
            if (!node) return;
            if (node.group === 'support') {
                openDetailPanel(id);
            } else {
                closeDetailPanel();
                // Keep URL hash in sync for deep-linking.
                if (history && history.replaceState) {
                    history.replaceState(null, '', `#${id}`);
                }
            }
        },
    });

    // Hero terminal — small, placeholder-only.
    initTerminal({ elementId: 'hero-term', lines: HERO_LINES, speed: 'slow' });

    // Per-module terminals with real snippets.
    const snippetMap = [
        ['term-digigraph',  'snippets/digigraph.py.txt',  'py'],
        ['term-digiquant',  'snippets/digiquant.py.txt',  'py'],
        ['term-digisearch', 'snippets/digisearch.py.txt', 'py'],
        ['term-digichat',   'snippets/digichat.ts.txt',   'ts'],
    ];

    for (const [elementId, path, lang] of snippetMap) {
        // Wire each terminal to its real-code snippet. Lazy: only start typing
        // when the act section enters view.
        const host = document.getElementById(elementId);
        if (!host) continue;
        let started = false;
        const obs = new IntersectionObserver(async (entries) => {
            for (const e of entries) {
                if (e.isIntersecting && !started) {
                    started = true;
                    const lines = await loadSnippet(path, lang);
                    initTerminal({ elementId, lines, speed: 'fast' });
                    obs.disconnect();
                }
            }
        }, { threshold: 0.3 });
        const parentAct = host.closest('.act');
        if (parentAct) obs.observe(parentAct);
    }

    // Detail-panel close wiring.
    const closeBtn = document.querySelector('.detail-close');
    if (closeBtn) closeBtn.addEventListener('click', closeDetailPanel);
    document.addEventListener('keydown', (e) => {
        if (e.key === 'Escape') closeDetailPanel();
    });

    initEcosystemToggles();
    initScrollActs(diagram);
    initTypographyMotion();

    // Deep-link support: if URL already has a module hash, focus it.
    const hash = window.location.hash.replace('#', '');
    if (hash && NODES.some((n) => n.id === hash)) {
        // Defer so the diagram layout + scroll are settled.
        setTimeout(() => diagram.focus(hash), 300);
    }
});
