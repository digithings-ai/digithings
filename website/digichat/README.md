# DigiChat on GitHub Pages (`/digichat/`)

This folder is **not** a second chat implementation. Production **DigiChat** is the **Next.js** app at repo root **`digichat/`** (see **[DIGICHAT.md](../../DIGICHAT.md)**).

## What this page does

- Serves **`index.html`** at **`https://&lt;your-pages&gt;/digichat/`** with links to the home page and docs.
- If **`redirect.json`** contains a non-empty **`url`**, the browser is sent there (your deployed Next app).

## Configure redirect

The repo ships **`redirect.json`** with **`https://chat.digithings.ai`** — point your Next deployment and DNS (CNAME) there, or edit **`url`** to match wherever **`digichat/`** is actually hosted.

For **local testing** of this HTML only, use **`redirect.local.json`** (gitignored) with e.g. `"url": "http://127.0.0.1:3000"`, or temporarily set **`url`** to **`""`** in **`redirect.json`** to disable auto-redirect and use the on-page links.

### CI (optional)

Repo variable **`DIGICHAT_PUBLIC_URL`** overrides **`redirect.json`** on Pages deploy (see **`.github/workflows/static.yml`**). Use that if you prefer not to commit environment-specific origins.

## Local quick check

From repo root:

```bash
cd website && python3 -m http.server 5173
```

Open `http://127.0.0.1:5173/digichat/`.
