# digichat deployment config examples

Copy one of these to the container bind-mount (default
`DIGICHAT_CONFIG_PATH=/app/config/digichat.yaml`). Overlay secrets via env
(`DIGICHAT_EMBED_TOKEN`, `DIGICHAT_HOST_<SLUG>_TOKEN`).

Canonical copies live in `frontend/digichat/config/examples/`:

- `digithings-ai-embed.yaml` — digithings.ai public embed
- `occ-embed.yaml` — OCC corpus embed
- `dashboard-modal.yaml` — dashboard / widget modal chrome
- `local-app.yaml` — Auth.js app + server persistence
- `skins/<id>.yaml` — one complete file per official assistant-ui template
  (also baked into the image at `/app/config/examples/skins/<id>.yaml`)

`DIGICHAT_EMBED_TENANTS` JSON remains a migration overlay into the same schema.
`DIGICHAT_CHROME_SKIN=claude` overlays `chrome.skin` without editing YAML.
A `skins/<id>.yaml` `deployment:` is the live `/embed` + `POST /api/chat`
tenant for a single client container.
