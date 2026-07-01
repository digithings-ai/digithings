# DigiVault – Obsidian-style markdown vault management for the Digi ecosystem
# Build from repo root: docker compose build digivault (context: .)
# See digivault/ARCHITECTURE.md. HTTP API + MCP tooling for DigiGraph.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src
RUN uv pip install --system -e "./digibase"

COPY digikey/pyproject.toml digikey/README.md ./digikey/
COPY digikey/src ./digikey/src
RUN uv pip install --system -e "./digikey"

COPY digivault/pyproject.toml digivault/ARCHITECTURE.md ./digivault/
COPY digivault/src ./digivault/src
WORKDIR /app/digivault
RUN uv pip install --system -e ".[service,supabase]"

WORKDIR /app
EXPOSE 8004
CMD ["uvicorn", "digivault.server:app", "--host", "0.0.0.0", "--port", "8004"]
