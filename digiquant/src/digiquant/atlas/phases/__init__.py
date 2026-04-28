"""Atlas sub-graph phase modules.

Each phase maps to a section of ``digiquant/src/digiquant/atlas/docs/agentic/ARCHITECTURE.md``:

- ``preflight`` — config load, prior context, data-layer probe.
- ``phase1_altdata`` — 4 alt-data nodes (sentiment, CTA, options, politician).
- ``phase2_institutional`` — 2 institutional nodes (flows, hedge funds).
- ``phase3_macro`` — single macro-regime node (commit 5).
- ``phase4_assetclass`` — 5 asset-class nodes (commit 5).
- ``phase5_equities`` — US equity + 11-sector swarm (commit 6).
- ``phase6_consolidate`` / ``phase7_*`` / ``phase9_evolution`` — commits 7–8.

Each phase module exposes ``build_nodes()`` — a sequence of ``NodeSpec`` the
pipeline builder wires into the StateGraph.
"""
