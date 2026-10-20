# digitrace – backend-neutral observability control plane (tracing helpers + status API)
# Build from repo root: docker compose build digitrace (context: .)
# See digitrace/ARCHITECTURE.md and root SECURITY.md. Bind to 127.0.0.1 in production via compose.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src
RUN uv pip install --system -e "./digibase"

COPY digitrace/pyproject.toml digitrace/ARCHITECTURE.md ./digitrace/
COPY digitrace/src ./digitrace/src
WORKDIR /app/digitrace
RUN uv pip install --system -e ".[tracing]"

EXPOSE 8003
CMD ["uvicorn", "digitrace.server:app", "--host", "0.0.0.0", "--port", "8003"]
