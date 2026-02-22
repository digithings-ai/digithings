# DigiGraph – Phase 0+ (LangGraph orchestration + MCP/HTTP)
# See DIGIGRAPH.md, SECURITY.md. Bind to 127.0.0.1 in production.

FROM python:3.12-slim

RUN apt-get update && apt-get install -y --no-install-recommends curl && rm -rf /var/lib/apt/lists/*

WORKDIR /app

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

RUN pip install --upgrade pip && pip install uv

COPY pyproject.toml ./
COPY src ./src
RUN uv pip install --system -e .

EXPOSE 8000
CMD ["uvicorn", "digigraph.server:app", "--host", "0.0.0.0", "--port", "8000"]
