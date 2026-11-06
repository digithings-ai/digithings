# digisearch – RAG, document search for Digi ecosystem
# Build from repo root: docker compose build digisearch (context: .)
# See digisearch/ARCHITECTURE.md. HTTP API + MCP tooling for digigraph.

FROM python:3.12-slim

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install "uv==0.12.24"
COPY pyproject.toml uv.lock ./

COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src

COPY digikey/pyproject.toml digikey/README.md ./digikey/
COPY digikey/src ./digikey/src

COPY digifetch/pyproject.toml digifetch/ARCHITECTURE.md ./digifetch/
COPY digifetch/src ./digifetch/src

COPY digibot/pyproject.toml digibot/ARCHITECTURE.md ./digibot/
COPY digibot/src ./digibot/src

# Workspace metadata only: digillm is deliberately not installed (DIG-1407), but
# uv's frozen export still needs the member's pyproject to parse the workspace.
COPY digillm/pyproject.toml digillm/ARCHITECTURE.md ./digillm/

# digillm is deliberately NOT a sibling here (DIG-1407): the board ruled that the
# deployed image does not need the remote embedding path, and digillm's hard deps would
# drag openai in and make that path importable for the first time. The web-research /
# websets call sites into digillm.client (web/answer.py, web/structured.py,
# websets/verify.py, websets/enrich.py) stay behind their lazy import guards, exactly as
# before. digillm is declared in the [embedding] extra, which this image does not install.

COPY digisearch/pyproject.toml digisearch/ARCHITECTURE.md ./digisearch/
COPY digisearch/src ./digisearch/src
COPY digisearch/seeds ./digisearch/seeds
WORKDIR /app/digisearch
# [server] = FastAPI/uvicorn/mcp/typer/digikey/digibot + json logging (base is now light);
# [ingestion] = parser deps incl. pdfplumber for PDF ingest; [azure]+[minilm] backend;
# [minilm] = ONNX embeddings without Chroma; [web-search] =
# ddgs fallback + digifetch fetch + trafilatura/readability extract.
# The constraints file is the frozen lock, so patched pins ship even though the
# image installs the workspace packages in editable mode.
RUN set -eux; \
    uv export --frozen --package digisearch \
      --extra server --extra ingestion --extra azure --extra minilm --extra web-search \
      --no-hashes --no-emit-project > /tmp/constraints.raw; \
    grep -v '^-e ' /tmp/constraints.raw | grep -v '^#' | grep -v '^$' > /tmp/constraints.txt; \
    test -s /tmp/constraints.txt; \
    uv pip install --system --no-cache -c /tmp/constraints.txt \
      -e "/app/digibase" -e "/app/digikey" -e "/app/digifetch" -e "/app/digibot" \
      -e ".[server,ingestion,azure,minilm,web-search]"

EXPOSE 8002
CMD ["uvicorn", "digisearch.server:app", "--host", "0.0.0.0", "--port", "8002"]
