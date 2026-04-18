#!/bin/bash
# watchlist-check.sh — Print the prompt for a quick watchlist health check
# Use this mid-week when you don't want a full digest
# Usage: ./scripts/watchlist-check.sh

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

DATE=$(date +%Y-%m-%d)
TIME=$(date +%H:%M)

echo ""
echo "📋 Watchlist Health Check — $DATE $TIME"
echo "==========================================="
echo ""
echo "PASTE THIS INTO CLAUDE:"
echo "-------------------------------------------"
echo ""
echo "Quick watchlist health check for $DATE."
echo ""
echo "Read config/watchlist.md and config/preferences.md."
echo ""
echo "For each asset in my watchlist:"
echo "1. Search for current price and % change today"
echo "2. Flag any that are at or near key technical levels"
echo "3. Flag any with news or catalyst"
echo "4. Flag anything that's moved >2% in either direction"
echo ""
echo "Output as a concise table. Under 200 words total."
echo "Do NOT update memory files for this — it's a quick scan."
echo ""
echo "-------------------------------------------"
echo ""
