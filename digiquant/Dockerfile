# digiquant – NautilusTrader + Polars quant pipeline
# Build from repo root: docker compose build digiquant (context: .)
# See digiquant/ARCHITECTURE.md and root SECURITY.md. Bind to 127.0.0.1 in production.
#
# Image ships digiquant[nautilus] like peer module images (digikey, digigraph):
# install package + extras only — no network fetch of upstream Nautilus fixtures.
# Sample market CSVs for backtests live under digiquant/data/ (compose-mounted).

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

COPY digiquant/pyproject.toml ./
COPY digiquant/src ./src
COPY digiquant/data ./data
RUN uv pip install --system -e ".[nautilus]"

EXPOSE 8001
CMD ["uvicorn", "digiquant.server:app", "--host", "0.0.0.0", "--port", "8001"]
