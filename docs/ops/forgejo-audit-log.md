# Forgejo audit logging (localhost:3000)

- Config: `/data/gitea/conf/app.ini` inside volume `local-forge_forgejo-data`.
  `[log] MODE = console, file`, `LEVEL = info`, `LOGGER_ACCESS_MODE = access`,
  plus `[log.file]` (forgejo.log) and `[log.access]` (access.log) writer
  sections. `ENABLE_ACCESS_LOG = true` (server) and `MAX_DAYS = 30`.
- Location inside container: `/data/gitea/log/`. On host: via the named volume
  `local-forge_forgejo-data` (mount `/data`).
- Retention: 30 days, daily rotation, gzip compression (`MAX_DAYS=30`,
  `DAILY_ROTATE=true`, `COMPRESS=true`).
- Access log template records remote host, identity (SignedUserName or `-`),
  timestamp, method, URL, status, size, referer, user agent, request id.
- What is NOT logged: 2FA secret values, token values, passwords. Forgejo never
  records the `Sudo` header on reviews or in any readable endpoint (see
  digiforge/internal/forge forge.go note).

## Review procedure
1. `docker exec -u git "${FORGEJO_CONTAINER:-local-forge-forgejo-1}" tail -n 200 /data/gitea/log/access.log`
2. Filter for admin actions: `grep -E "POST|PUT|DELETE|PATCH" access.log | grep -v " 200 \| 201 \| 204 "` (non-2xx mutations).
3. Check for failed auth: `grep " 401 \| 403 " access.log`.
4. Archive monthly: copy the volume's log dir to a dated backup before rotation
   purges it (30-day window).

## Backup
docker compose stop forgejo
docker run --rm -v local-forge_forgejo-data:/data -v "$HOME/Backups":/backup alpine \
  tar czf /backup/forgejo-logs-$(date +%Y%m%d).tgz -C /data/log .
docker compose start forgejo
