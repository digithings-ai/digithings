#!/bin/bash
# memory-search.sh — Search all rolling memory files for a keyword or topic
# Usage: ./scripts/memory-search.sh "keyword"
# Example: ./scripts/memory-search.sh "yield curve"
#          ./scripts/memory-search.sh "BTC"
#          ./scripts/memory-search.sh "Fed"

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

QUERY=${1:-""}

if [ -z "$QUERY" ]; then
  echo "Usage: ./scripts/memory-search.sh \"keyword\""
  echo "Searches all memory/*/ROLLING.md files for the given term."
  exit 1
fi

echo ""
echo "🔍 Memory Search: \"$QUERY\""
echo "================================="
echo ""

for FILE in $(find memory/ -name "ROLLING.md" | sort); do
  SEGMENT=$(echo "$FILE" | sed 's|memory/||' | sed 's|/ROLLING.md||')
  MATCHES=$(grep -in "$QUERY" "$FILE" 2>/dev/null || true)
  
  if [ -n "$MATCHES" ]; then
    echo "📁 $SEGMENT:"
    # Print matched lines with context (3 lines before/after)
    grep -in -A2 -B2 "$QUERY" "$FILE" | head -30
    echo ""
  fi
done

echo ""
echo "---"
echo "To see full context, open the relevant memory file directly."
echo ""
