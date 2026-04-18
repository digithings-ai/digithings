#!/bin/bash
# thesis.sh — Helper for managing active theses in preferences.md
# Usage:
#   ./scripts/thesis.sh list          — Show current theses
#   ./scripts/thesis.sh add           — Print prompt to add a new thesis
#   ./scripts/thesis.sh close         — Print prompt to close/archive a thesis
#   ./scripts/thesis.sh review        — Print prompt for a full thesis review

set -e
[[ "${1:-}" == '--help' || "${1:-}" == '-h' ]] && { grep '^#' "$0" | tail -n +2 | sed 's/^#[[:space:]]\{0,1\}//'; exit 0; }

ACTION=${1:-list}
DATE=$(date +%Y-%m-%d)

case "$ACTION" in

  list)
    echo ""
    echo "📌 Active Theses — from config/preferences.md"
    echo "================================================"
    # Extract thesis section from preferences.md
    awk '/## 📌 Current Portfolio Themes/,/^---/' config/preferences.md | grep "^\-" | head -20
    echo ""
    ;;

  add)
    echo ""
    echo "➕ Add New Thesis"
    echo "=================="
    echo ""
    read -p "Describe the thesis in one line: " THESIS
    echo ""
    echo "PASTE THIS INTO CLAUDE:"
    echo "-------------------------------------------"
    echo "Add this thesis to config/preferences.md under 'Current Portfolio Themes':"
    echo ""
    echo "- $THESIS (opened $DATE)"
    echo ""
    echo "Then confirm it's been added and ask if I want to run a quick supporting analysis."
    echo "-------------------------------------------"
    echo ""
    ;;

  close)
    echo ""
    echo "❌ Close a Thesis"
    echo "=================="
    echo ""
    echo "Current theses:"
    awk '/## 📌 Current Portfolio Themes/,/^---/' config/preferences.md | grep "^\-" | head -20
    echo ""
    read -p "Which thesis to close (copy/paste it): " THESIS
    echo ""
    echo "PASTE THIS INTO CLAUDE:"
    echo "-------------------------------------------"
    echo "Close this thesis in config/preferences.md:"
    echo ""
    echo "  $THESIS"
    echo ""
    echo "Remove it from the active list. Then add a closing note to the relevant"
    echo "memory ROLLING.md file: what was the outcome, was the thesis correct,"
    echo "and what did we learn? Date: $DATE."
    echo "-------------------------------------------"
    echo ""
    ;;

  review)
    echo ""
    echo "🔍 Thesis Review"
    echo "================="
    echo ""
    echo "PASTE THIS INTO CLAUDE:"
    echo "-------------------------------------------"
    echo "Run a thesis review for $DATE per skills/SKILL-thesis-tracker.md."
    echo "Read config/preferences.md for active theses."
    echo "Read all memory/*/ROLLING.md files for recent context."
    echo "Score each thesis and give me a portfolio-level summary."
    echo "-------------------------------------------"
    echo ""
    ;;

  *)
    echo "Usage: ./scripts/thesis.sh [list|add|close|review]"
    exit 1
    ;;
esac
