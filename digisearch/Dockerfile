# DigiSearch – RAG, document search for Digi ecosystem
# See DIGISEARCH.md. HTTP API + MCP tooling for DigiGraph/DigiFlow.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system -e ".[azure]"

EXPOSE 8002
# HTTP API (primary). MCP: run `digisearch mcp --port 8765` for MCP server.
CMD ["uvicorn", "digisearch.server:app", "--host", "0.0.0.0", "--port", "8002"]
