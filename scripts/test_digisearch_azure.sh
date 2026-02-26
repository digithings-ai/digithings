#!/usr/bin/env bash
# Test DigiSearch with Azure AI Search.
# Usage: Set env vars (or .env) then run:
#   AZURE_SEARCH_ENDPOINT=https://... AZURE_SEARCH_API_KEY=... AZURE_SEARCH_INDEX_NAME=... ./scripts/test_digisearch_azure.sh
# Or: source .env && ./scripts/test_digisearch_azure.sh

set -e
cd "$(dirname "$0")/.."

echo "=== DigiSearch Azure test ==="
echo ""

# Check env
for v in AZURE_SEARCH_ENDPOINT AZURE_SEARCH_API_KEY AZURE_SEARCH_INDEX_NAME; do
  if [ -z "${!v}" ]; then
    echo "Missing: $v"
    echo "Set in .env or: export $v=..."
    exit 1
  fi
done

# Install azure backend if needed
uv pip install -e "digisearch[azure]" -q 2>/dev/null || pip install -e "digisearch[azure]" -q 2>/dev/null || true

echo "1. Testing Azure status (GET /azure_status)..."
if command -v curl &>/dev/null; then
  curl -s "http://127.0.0.1:8002/azure_status" 2>/dev/null | python3 -m json.tool || echo "Start DigiSearch first: uv run uvicorn digisearch.server:app --port 8002"
else
  echo "curl not found; start server and hit http://127.0.0.1:8002/azure_status"
fi

echo ""
echo "2. Testing query (POST /query)..."
echo "Run with DigiSearch server up:"
echo '  curl -X POST http://127.0.0.1:8002/query -H "Content-Type: application/json" -d '\''{"text":"your search term","top_k":5}'\'' | python3 -m json.tool'
echo ""
echo "Or run server in one terminal: uv run uvicorn digisearch.server:app --port 8002"
echo "Then run this script again."
