# .vulture_whitelist.py — False-positive suppression for find_stale.py (vulture)
#
# Add entries here when vulture flags something that IS used but accessed
# dynamically: Pydantic model fields, MCP tool registrations, LangGraph state
# fields, FastAPI route handlers, etc.
#
# Format: import the symbol and reference it with a comment explaining why.
# See: https://github.com/jendrikseipp/vulture#whitelists
#
# Run: make find-stale
# Apply: python3 scripts/find_stale.py --whitelist .vulture_whitelist.py

# ── DigiGraph ─────────────────────────────────────────────────────────────────

# LangGraph TypedDict state fields — accessed by graph nodes via state["field"]
# and serialized/deserialized by the checkpoint backend. Vulture can't see these.
# from digigraph.models import WorkflowState
# WorkflowState.workflow_id   # checkpoint serialization
# WorkflowState.messages      # supervisor node reads/writes
# WorkflowState.request_id    # span attribute propagation
# WorkflowState.session_id    # audit trail

# MCP tool functions — registered dynamically via the MCP registry, not called
# directly from Python code. Vulture sees them as unused because the call comes
# from LangGraph's tool node at runtime.
# from digigraph.orchestration.builtin import search_tool, execute_tool
# search_tool   # registered via MCP registry
# execute_tool  # registered via MCP registry

# ── DigiSmith ────────────────────────────────────────────────────────────────

# configure_tracer is called at service startup via import side-effect in main.py
# Vulture flags it as unused because it's not called within the library itself.
# from digismith.tracer import configure_tracer
# configure_tracer  # called at service startup

# ── DigiSearch ────────────────────────────────────────────────────────────────

# Backend classes are registered in the backend registry and instantiated via
# string lookup — vulture can't see the dynamic dispatch.
# from digisearch.backends.qdrant import QdrantBackend
# QdrantBackend  # registered in backend registry

# ── DigiKey ───────────────────────────────────────────────────────────────────

# FastAPI route handlers decorated with @router.get / @router.post are called
# by the ASGI framework, not from Python code directly.
# (vulture usually handles these correctly via its FastAPI plugin;
#  add entries here only if you see false positives)

# ── DigiBase ──────────────────────────────────────────────────────────────────

# ApiErrorEnvelope fields are serialized to JSON via .model_dump() — Pydantic
# accesses them dynamically so vulture may flag them as unused attributes.
# from digibase.models import ApiErrorEnvelope
# ApiErrorEnvelope.error    # JSON response field
# ApiErrorEnvelope.detail   # JSON response field
# ApiErrorEnvelope.code     # JSON response field

# ── Triage log (issue #15, 2026-04-18) ────────────────────────────────────────
#
# make find-stale reported 199 candidates at ≥60% confidence. Manual triage:
#
# DELETED (true positives):
#   digisearch/src/digisearch/ingestion/parsers/markdown.py
#     - `import mistune` + `_MISTUNE_AVAILABLE` (90% confidence): never used;
#       MarkdownParser reads files as plain text without calling mistune at all.
#
# KEPT — false positives by category:
#   FASTAPI  (60%): all server.py route functions in digigraph, digisearch,
#            digiquant, digikey, digismith — FastAPI/Starlette wires them via
#            decorator; vulture cannot trace the ASGI registration.
#   MCP      (60%): mcp_server.py functions in digigraph, digiquant, digisearch
#            — registered via @server.list_tools / @server.call_tool decorators.
#   NAUTILUS (60%): strategy on_start / on_bar / on_reset — NautilusTrader
#            framework calls these via C-extension dispatch, not Python callsites.
#   SCHEMA   (60%): TypedDict / Pydantic model fields (WorkflowState, models.py)
#            — accessed dynamically via state["field"] or .model_dump().
#   PUBLIC   (60%): library functions with no internal callers but part of the
#            public API surface (e.g. load_public_key_from_pem, decode_token_local,
#            export_to_pine, generate_param_grid, clear_backtest_cache).
#   STUB     (60%): interface method stubs in brokers/base.py and brokers/stubs.py;
#            disconnect() / place_order() are protocol members, kept for type safety.
#   UNUSED_ARG (100%): exc_tb, exc_val in __exit__; frame, signum in signal handler;
#            param in @click.pass_context — required by protocol, not usable.
#
# Next run: `make find-stale` — 197 of the 199 candidates should remain
# (the 2 deleted entries: mistune import + _MISTUNE_AVAILABLE flag).
# Add --min-confidence 80 to filter signal from noise.
