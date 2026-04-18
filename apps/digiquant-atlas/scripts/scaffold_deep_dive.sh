#!/bin/bash
# scaffold_deep_dive.sh — Create data/agent-cache/deep-dives/<stem>.json skeleton (deep_dive schema)
# Usage: ./scripts/scaffold_deep_dive.sh YYYY-MM-DD "Short Title Slug"
# Example: ./scripts/scaffold_deep_dive.sh 2026-04-10 "Oil-Hormuz-Risk"

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

DATE="${1:?date YYYY-MM-DD}"
TITLE="${2:?title slug}"
STEM="${DATE}-${TITLE// /-}"
OUT="data/agent-cache/deep-dives/${STEM}.json"
GEN=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

mkdir -p data/agent-cache/deep-dives
cat > "$OUT" << EOF
{
  "schema_version": "1.0",
  "doc_type": "deep_dive",
  "date": "${DATE}",
  "title": "${TITLE}",
  "meta": {
    "generated_at": "${GEN}",
    "tags": [],
    "tickers": [],
    "source_refs": []
  },
  "body": {
    "summary": "",
    "sections": [],
    "markdown": "# ${TITLE}\\n\\n_Fill body.markdown with the full report._\\n"
  }
}
EOF

echo "Wrote $OUT — edit body.markdown; validate: python3 scripts/validate_artifact.py $OUT"
