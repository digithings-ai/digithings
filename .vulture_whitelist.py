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
