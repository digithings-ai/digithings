#!/usr/bin/env bash
# Build Docker stack, bring it up, then run a workflow example (curl POST /workflow).
# Requires Docker to be running.
set -e
cd "$(dirname "$0")/.."

echo "Building Docker images (DigiQuant with Nautilus + test data may take a few minutes)..."
docker compose build

echo "Starting stack..."
docker compose up -d

echo "Waiting for DigiGraph and DigiQuant to be healthy..."
for i in {1..30}; do
  if curl -sf http://127.0.0.1:8000/health >/dev/null && curl -sf http://127.0.0.1:8001/health >/dev/null; then
    echo "Stack is up."
    break
  fi
  [ "$i" -eq 30 ] && { echo "Timeout waiting for services"; exit 1; }
  sleep 2
done

echo ""
echo "Running workflow example: POST /workflow"
echo "Prompt: Build me a mean-reversion stat-arb on tech"
echo ""
curl -s -X POST http://127.0.0.1:8000/workflow \
  -H "Content-Type: application/json" \
  -d '{"prompt":"Build me a mean-reversion stat-arb on tech","session_id":"docker-example"}' | python3 -m json.tool

echo ""
echo "Done. Stop with: docker compose down"
