# DigiQuant – Phase 0+ (Nautilus + Polars)
# See DIGIQUANT.md, SECURITY.md. Bind to 127.0.0.1 in production.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

COPY pyproject.toml ./
COPY src ./src
COPY data ./data
# Real backtests by default. Set NAUTILUS=0 to build without NautilusTrader.
ARG NAUTILUS=1
RUN if [ "$NAUTILUS" = "1" ]; then uv pip install --system -e ".[nautilus]"; else uv pip install --system -e .; fi

# Nautilus test data so backtest works in container (TestDataProvider expects site-packages/tests/test_data/...)
ARG NAUTILUS=1
RUN if [ "$NAUTILUS" = "1" ]; then \
  NTEST=$(python3 -c "import nautilus_trader; from pathlib import Path; p=Path(nautilus_trader.__file__).resolve().parent.parent/'tests'/'test_data'/'binance'; print(p)"); \
  mkdir -p "$NTEST" && curl -sfL -o "$NTEST/ethusdt-trades.csv" "https://raw.githubusercontent.com/nautechsystems/nautilus_trader/develop/tests/test_data/binance/ethusdt-trades.csv" && \
  test -s "$NTEST/ethusdt-trades.csv" || (echo "Failed to download Nautilus test data" && exit 1); \
  fi

# Default: run HTTP server for DigiGraph (MCP in Phase 2)
EXPOSE 8001
CMD ["uvicorn", "digiquant.server:app", "--host", "0.0.0.0", "--port", "8001"]
