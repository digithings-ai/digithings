# DigiSearch – RAG, document search for Digi ecosystem
# Build from repo root: docker compose build digisearch (context: .)
# See digisearch/ARCHITECTURE.md. HTTP API + MCP tooling for DigiGraph.

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

COPY digisearch/pyproject.toml digisearch/ARCHITECTURE.md ./digisearch/
COPY digisearch/src ./digisearch/src
COPY digisearch/seeds ./digisearch/seeds
WORKDIR /app/digisearch
RUN uv pip install --system -e ".[azure,chroma]"

EXPOSE 8002
CMD ["uvicorn", "digisearch.server:app", "--host", "0.0.0.0", "--port", "8002"]
