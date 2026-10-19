# digiquant – NautilusTrader + Polars quant pipeline
# Build from repo root: docker compose build digiquant (context: .)
# See digiquant/ARCHITECTURE.md and root SECURITY.md. Bind to 127.0.0.1 in production.
#
# Image ships digiquant[nautilus] like peer module images (digikey, digigraph):
# install package + extras only — no network fetch of upstream Nautilus fixtures.
# Sample market CSVs for backtests live under digiquant/data/ (compose-mounted).
#
# Reproducibility (DIG-2303): third-party packages install frozen from the
# repo-root uv.lock (ADR-0033, the single authoritative lock) via
# `uv export --frozen`, so rebuilds of an unchanged commit resolve the
# identical package set — the same set CI installs. Only the nautilus_trader
# engine version itself is additionally pinned in digiquant/pyproject.toml.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

# Workspace root metadata + the single authoritative lock. Only the member
# trees this image installs are copied; `uv export --frozen` tolerates the
# pruned workspace (measured: rc=0, --offline clean).
COPY pyproject.toml uv.lock ./
COPY digibase/pyproject.toml digibase/README.md ./digibase/
COPY digibase/src ./digibase/src
COPY digikey/pyproject.toml digikey/README.md ./digikey/
COPY digikey/src ./digikey/src
COPY digifetch/pyproject.toml digifetch/ARCHITECTURE.md ./digifetch/
COPY digifetch/src ./digifetch/src
COPY digiquant/pyproject.toml ./digiquant/
COPY digiquant/src ./digiquant/src
COPY digiquant/data ./data

# Frozen, hash-pinned install: `uv export --frozen` renders the root lock's
# digiquant[nautilus,mcp] subset (no lock update, no network) and
# `uv pip install -r` installs exactly those pins, hash-verified.
RUN uv export --frozen --package digiquant --extra nautilus --extra mcp --no-dev -o /tmp/digiquant-reqs.txt \
 && uv pip install --system -r /tmp/digiquant-reqs.txt \
 && rm -f /tmp/digiquant-reqs.txt

EXPOSE 8001
CMD ["uvicorn", "digiquant.server:app", "--host", "0.0.0.0", "--port", "8001"]
