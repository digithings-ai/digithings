#!/bin/sh
# Wait for Redis, then start digikey (startup rehydrate needs Redis when URL is set).
set -eu

i=0
while [ "$i" -lt 30 ]; do
  if redis-cli -h 127.0.0.1 -p 6379 ping 2>/dev/null | grep -q PONG; then
    break
  fi
  i=$((i + 1))
  sleep 1
done

exec uvicorn digikey.server:app --host 0.0.0.0 --port 8005
