# DigiClaw – heartbeat runner + JSONL audit log
# Build from repo root: docker compose build digiclaw (context: .)
# See digiclaw/ARCHITECTURE.md.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

# Shared digibase (audit redaction helpers)
COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src
RUN uv pip install --system -e "./digibase"

COPY digiclaw/pyproject.toml digiclaw/ARCHITECTURE.md ./digiclaw/
COPY digiclaw/src ./digiclaw/src
RUN uv pip install --system -e "./digiclaw"

HEALTHCHECK --interval=60s --timeout=5s --start-period=10s \
  CMD python3 -c "import digiclaw" || exit 1

CMD ["python3", "-m", "digiclaw"]
