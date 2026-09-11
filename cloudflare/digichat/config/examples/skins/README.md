# Catalog template deploys

Each file is a complete `digichat.yaml` for one Thread skin: the 11 official
assistant-ui catalog templates plus first-party `digichat`.
Copy into the container (or point `DIGICHAT_CONFIG_PATH` at the baked copy).
That file **is** the running product: `/embed` (or `/` for layout templates)
mounts that Thread and `POST /api/chat` uses this deployment. No
`DIGICHAT_EMBED_TENANTS` entry is required.

```bash
# Overlay only (keeps the rest of your YAML):
DIGICHAT_CHROME_SKIN=claude

# Baked example inside the image:
DIGICHAT_CONFIG_PATH=/app/config/examples/skins/claude.yaml

# Bind-mount your own file:
#   ./digichat.yaml:/app/config/digichat.yaml:ro
DIGICHAT_CONFIG_PATH=/app/config/digichat.yaml
```

Thread templates (`base`, clones, `base-assistant-ui`, `react-ink`) default to
`chrome.mode: embed` so `/` redirects to `/embed` and the iframe is the product.
Layout templates (`webpage-assistant`, `product-page-assistant`, `expo-react-native`)
use `chrome.mode: app` so they own `/`.

Chat still goes through `POST /api/chat` (BFF). Secrets stay in env, not these files.
