#!/usr/bin/env bash
# Run the workflow e2e test. Assumes DigiQuant (8001) and DigiGraph (8000) are already up.
# Start them with:
#   PYTHONPATH=digiquant/src:digigraph/src:. python -m uvicorn digiquant.server:app --host 127.0.0.1 --port 8001 &
#   PYTHONPATH=digiquant/src:digigraph/src:. DIGIQUANT_URL=http://127.0.0.1:8001 python -m uvicorn digigraph.server:app --host 127.0.0.1 --port 8000 &
# Or: docker compose up -d
set -e
cd "$(dirname "$0")/.."
echo "Running workflow e2e test (DigiQuant + DigiGraph must be up on 8001 and 8000)..."
python -m pytest tests/test_e2e.py -v -m e2e --tb=short
echo "Done."
