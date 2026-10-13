#!/bin/bash
# DIG-2366 rehearsal store stager.
#
# Builds rehearsal/data-run: an isolated copy of the pinned 2026.1001.0 CLI
# install plus an instance config pinned to PORT/PGPORT, so run-rehearsal.sh can
# boot a control and a patched instance without ever touching ~/.paperclip/cli
# or the live instance.
#
# data-run is gitignored and rebuilt from scratch on every run, so a rehearsal
# is reproducible on a clean machine: ./stage-store.sh && ./run-rehearsal.sh
set -euo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
DATA="$HERE/data-run"
LIVE_CLI="${DIG2366_LIVE_CLI:-$HOME/.paperclip/cli}"
VER="2026.1001.0"
PORT=3199
PGPORT=54339
INST_ID=dig2366

log() { printf '%s\n' "$*"; }

LIVE_INSTALL="$LIVE_CLI/installs/npm/$VER"
[ -d "$LIVE_INSTALL/node_modules/paperclipai" ] || { log "missing live install $LIVE_INSTALL"; exit 1; }

log "rebuilding $DATA"
rm -rf "$DATA"
mkdir -p "$DATA/cli/installs/npm"

# APFS clone keeps the 1.4G copy cheap; fall back to a plain copy elsewhere.
if ! cp -Rc "$LIVE_INSTALL" "$DATA/cli/installs/npm/$VER" 2>/dev/null; then
  cp -R "$LIVE_INSTALL" "$DATA/cli/installs/npm/$VER"
fi

ln -s "installs/npm/$VER" "$DATA/cli/current"

cat > "$DATA/cli/install.json" <<JSON
{
  "schemaVersion": 1,
  "source": "npm",
  "version": "$VER",
  "channel": "pinned",
  "payloadPath": "$DATA/cli/installs/npm/$VER",
  "installedAt": "$(date -u +%Y-%m-%dT%H:%M:%S.000Z)",
  "previous": []
}
JSON

INST="$DATA/instances/$INST_ID"
mkdir -p "$INST/db" "$INST/logs" "$INST/secrets" \
         "$INST/data/storage" "$INST/data/backups"

# 32 bytes base64, matching the shape the CLI writes for local_encrypted keys.
for k in master.key decision-signing.key; do
  head -c 32 /dev/urandom | base64 > "$INST/secrets/$k"
done

cat > "$INST/.env" <<ENV
# Paperclip environment variables (DIG-2366 rehearsal instance)
PAPERCLIP_AGENT_JWT_SECRET=$(head -c 32 /dev/urandom | xxd -p | tr -d '\n')
PAPERCLIP_TOOL_ACTION_SIGNING_SECRET=$(head -c 32 /dev/urandom | xxd -p | tr -d '\n')
ENV
chmod 600 "$INST/.env" "$INST/secrets/"*.key

cat > "$INST/config.json" <<JSON
{
  "\$meta": { "version": 1, "updatedAt": "$(date -u +%Y-%m-%dT%H:%M:%S.336Z)", "source": "configure" },
  "database": {
    "mode": "embedded-postgres",
    "embeddedPostgresDataDir": "$INST/db",
    "embeddedPostgresPort": $PGPORT,
    "backup": { "enabled": false, "intervalMinutes": 60, "retentionDays": 30, "dir": "$INST/data/backups" }
  },
  "logging": { "mode": "file", "logDir": "$INST/logs" },
  "server": {
    "deploymentMode": "local_trusted",
    "exposure": "private",
    "bind": "loopback",
    "host": "127.0.0.1",
    "port": $PORT,
    "allowedHostnames": [],
    "serveUi": true
  },
  "telemetry": { "enabled": false },
  "updates": { "checkEnabled": false },
  "auth": { "baseUrlMode": "auto", "disableSignUp": false },
  "storage": {
    "provider": "local_disk",
    "localDisk": { "baseDir": "$INST/data/storage" },
    "s3": { "bucket": "paperclip", "region": "us-east-1", "prefix": "", "forcePathStyle": false }
  },
  "secrets": {
    "provider": "local_encrypted",
    "strictMode": false,
    "localEncrypted": { "keyFilePath": "$INST/secrets/master.key" }
  }
}
JSON

log "staged:"
log "  install   $DATA/cli/installs/npm/$VER"
log "  current   $DATA/cli/current -> installs/npm/$VER"
log "  instance  $INST/config.json (server :$PORT, postgres :$PGPORT)"
