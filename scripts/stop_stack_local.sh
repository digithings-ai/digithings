#!/usr/bin/env bash
# Kill processes started by run_stack_local.sh (PIDs in .local_stack_pids).
set -e
cd "$(dirname "$0")/.."
ROOT="$PWD"
PIDFILE="$ROOT/.local_stack_pids"
if [ ! -f "$PIDFILE" ]; then
  echo "No $PIDFILE — nothing to stop."
  exit 0
fi
while read -r pid; do
  [ -z "$pid" ] && continue
  case "$pid" in
    ''|*[!0-9]*) continue ;;
  esac
  if kill -0 "$pid" 2>/dev/null; then
    kill "$pid" 2>/dev/null || true
  fi
done < "$PIDFILE"
rm -f "$PIDFILE"
echo "Stopped local stack (DigiKey + LiteLLM + Python services from last run_stack_local)."
