#!/bin/bash
# scaffold_evolution_day.sh — Create data/agent-cache/evolution/YYYY-MM-DD/*.json scaffolds (post-mortem)
# Usage: ./scripts/scaffold_evolution_day.sh [YYYY-MM-DD]

set -e
DATE="${1:-$(date +%Y-%m-%d)}"
DIR="data/agent-cache/evolution/${DATE}"
mkdir -p "$DIR"

gen_ts=$(date -u +"%Y-%m-%dT%H:%M:%SZ")

cat > "${DIR}/quality-log.json" << EOF
{
  "schema_version": "1.0",
  "doc_type": "evolution_quality_log",
  "date": "${DATE}",
  "title": "Pipeline quality — ${DATE}",
  "meta": { "generated_at": "${gen_ts}", "tags": ["scaffold"] },
  "body": {
    "summary": "",
    "segments_updated": [],
    "segments_carried_forward": [],
    "triage_notes": "",
    "materialization_notes": "",
    "data_quality_notes": "",
    "phase_rating": "",
    "strengths": "",
    "weaknesses": ""
  }
}
EOF

cat > "${DIR}/sources.json" << EOF
{
  "schema_version": "1.0",
  "doc_type": "evolution_sources",
  "date": "${DATE}",
  "title": "Data source ratings — ${DATE}",
  "meta": { "generated_at": "${gen_ts}", "tags": ["scaffold"] },
  "body": {
    "source_ratings": [],
    "notes": ""
  }
}
EOF

cat > "${DIR}/proposals.json" << EOF
{
  "schema_version": "1.0",
  "doc_type": "evolution_proposals",
  "date": "${DATE}",
  "title": "Improvement proposals — ${DATE}",
  "meta": { "generated_at": "${gen_ts}", "tags": ["scaffold"] },
  "body": {
    "proposals": []
  }
}
EOF

echo "Scaffolded: ${DIR}/quality-log.json, sources.json, proposals.json"
echo "Fill JSON, then: python3 scripts/update_tearsheet.py (or run_db_first.py after publish rules)"
