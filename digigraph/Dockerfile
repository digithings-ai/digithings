# DigiGraph – Phase 0+ (LangGraph orchestration + MCP/HTTP)
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

# DigiKey (JWT verification middleware)
COPY digikey/pyproject.toml digikey/README.md ./digikey/
COPY digikey/src ./digikey/src
RUN uv pip install --system -e "./digikey"

# DigiSmith (sibling package; tracing helpers + LangSmith SDK)
COPY digismith/pyproject.toml digismith/ARCHITECTURE.md ./digismith/
COPY digismith/src ./digismith/src
RUN uv pip install --system -e "./digismith[langsmith]"

COPY digigraph/pyproject.toml ./digigraph/
COPY digigraph/src ./digigraph/src
# ECharts → SVG (optional): install JS deps for render_svg path; safe to fail if lockfile missing
RUN if [ -f digigraph/src/digigraph/tools/analytics/visualization/echarts/package-lock.json ]; then \
      cd digigraph/src/digigraph/tools/analytics/visualization/echarts && npm ci --omit=dev; \
    fi
RUN uv pip install --system -e "./digigraph"

EXPOSE 8000
CMD ["uvicorn", "digigraph.server:app", "--host", "0.0.0.0", "--port", "8000"]
