# digigraph – Phase 0+ (LangGraph orchestration + MCP/HTTP)
# Build from repo root: docker compose build digigraph (context: .)
# See digigraph/ARCHITECTURE.md and root SECURITY.md. Bind to 127.0.0.1 in production.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl nodejs npm \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

# digibase (shared HTTP/error/audit helpers)
COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src
RUN uv pip install --system -e "./digibase"

# digikey (JWT verification middleware)
COPY digikey/pyproject.toml digikey/README.md ./digikey/
COPY digikey/src ./digikey/src
RUN uv pip install --system -e "./digikey"

# digitrace (sibling package; tracing helpers + LangSmith SDK)
COPY digitrace/pyproject.toml digitrace/ARCHITECTURE.md ./digitrace/
COPY digitrace/src ./digitrace/src
RUN uv pip install --system -e "./digitrace[tracing]"

# digillm (sibling package; LLM client/provider abstraction — digigraph runtime dep)
COPY digillm/pyproject.toml digillm/ARCHITECTURE.md ./digillm/
COPY digillm/src ./digillm/src
RUN uv pip install --system -e "./digillm"

COPY digigraph/pyproject.toml ./digigraph/
COPY digigraph/src ./digigraph/src
# Required runtime config, baked in so a raw ghcr.io/.../digigraph image boots with
# zero configuration. Both are loaded at import time (not lazily) and both are
# fail-loud — a missing or malformed one crashes digigraph at startup rather than
# degrading:
#   byok-providers.json  llm_auth._load_byok_catalog   — BYOK provider allowlist
#   model-policy.json    model_config._load_model_policy — flagship markers + the
#                                                            mode ladder's last resort
# Their __file__-relative fallbacks resolve to /app/config/<file> under this image's
# WORKDIR/layout. Still overridable via a volume mount at /app/config or
# DIGI_CONFIG_PATH — but that mount REPLACES the whole directory, it does not merge
# with this baked-in copy, so it must supply these two plus model_modes.yaml. A
# mount missing either required file crash-loops digigraph at startup (by design —
# no silent fallback); a mount missing model_modes.yaml does NOT crash, because that
# loader degrades to an empty config and the ladder falls through to
# `fallback_model` from model-policy.json. Supply all three regardless.
COPY config/byok-providers.json ./config/byok-providers.json
COPY config/model-policy.json ./config/model-policy.json
# ECharts → SVG (optional): install JS deps for render_svg path; safe to fail if lockfile missing
RUN if [ -f digigraph/src/digigraph/tools/analytics/visualization/echarts/package-lock.json ]; then \
      cd digigraph/src/digigraph/tools/analytics/visualization/echarts && npm ci --omit=dev; \
    fi
# [mcp] extra: the remote-MCP client (orchestration/mcp_client.py) imports the
# `mcp` package; without it every X-Digi-Mcp-Servers server fails with
# "No module named 'mcp'". The stack-container image already ships it.
RUN uv pip install --system -e "./digigraph[mcp]"

EXPOSE 8000
CMD ["uvicorn", "digigraph.server:app", "--host", "0.0.0.0", "--port", "8000"]
