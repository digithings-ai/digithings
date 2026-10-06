# digisearch – RAG, document search for Digi ecosystem
# Build from repo root: docker compose build digisearch (context: .)
# See digisearch/ARCHITECTURE.md. HTTP API + MCP tooling for digigraph.

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

COPY digifetch/pyproject.toml digifetch/ARCHITECTURE.md ./digifetch/
COPY digifetch/src ./digifetch/src
RUN uv pip install --system -e "./digifetch"

COPY digiclaw/pyproject.toml digiclaw/ARCHITECTURE.md ./digiclaw/
COPY digiclaw/src ./digiclaw/src
RUN uv pip install --system -e "./digiclaw"

# digillm (sibling package; carries the keyed egress record the remote
# embedding path emits -- digillm.egress_record, one digest implementation for
# the whole stack). Installed as a sibling, before digisearch, so the import
# resolves in the image (DIG-1407).
#
# NOTE: this DOES put `openai` in the image, because digillm's own hard
# dependencies install with it and digillm/__init__.py imports digillm.client,
# which imports openai at module scope -- so `import digillm.egress_record`
# cannot resolve without it. The [embedding] extra placement in
# digisearch/pyproject.toml therefore does NOT keep openai out of the container;
# it only keeps it out of digisearch's base install. Whether the deployed
# digisearch image should have the remote embedding path at all is an open
# decision, routed to the EM on DIG-1407 -- do not read this line as settled.
COPY digillm/pyproject.toml digillm/ARCHITECTURE.md ./digillm/
COPY digillm/src ./digillm/src
RUN uv pip install --system -e "./digillm"

COPY digisearch/pyproject.toml digisearch/ARCHITECTURE.md ./digisearch/
COPY digisearch/src ./digisearch/src
COPY digisearch/seeds ./digisearch/seeds
WORKDIR /app/digisearch
# [server] = FastAPI/uvicorn/mcp/typer/digikey/digiclaw + json logging (base is now light);
# [ingestion] = parser deps incl. pdfplumber for PDF ingest; [azure]+[chroma] backends;
# [web-search] = ddgs fallback + digifetch fetch + trafilatura/readability extract.
RUN uv pip install --system -e ".[server,ingestion,azure,chroma,web-search]"

EXPOSE 8002
CMD ["uvicorn", "digisearch.server:app", "--host", "0.0.0.0", "--port", "8002"]
