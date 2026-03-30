# DigiChat on GitHub Pages (`/digichat/`)

This folder is **not** a second chat implementation. Production **DigiChat** is the **Next.js** app at repo root **`digichat/`** (see **[DIGICHAT.md](../../DIGICHAT.md)**).

## What this page does

- Serves **`index.html`** at **`https://&lt;your-pages&gt;/digichat/`** with links to the home page and docs.
- If **`redirect.json`** contains a non-empty **`url`**, the browser is sent there (your deployed Next app).

## Configure redirect

1. Copy **`redirect.example.json`** → **`redirect.json`** (or edit the committed **`redirect.json`** on your fork).
2. Set **`url`** to the **origin** of your running DigiChat (e.g. `https://chat.digithings.ai` or `http://127.0.0.1:3000` for local testing of this HTML only).

Leave **`url`** as **`""`** to disable auto-redirect; the page still shows manual links.

### CI (optional)

In the repo **Settings → Secrets and variables → Actions → Variables**, you can define **`DIGICHAT_PUBLIC_URL`**.  
**`.github/workflows/static.yml`** writes **`website/digichat/redirect.json`** before deploy when that variable is non-empty, so you do not have to commit the URL.

## Local quick check

From repo root:

```bash
cd website && python3 -m http.server 5173
```

Open `http://127.0.0.1:5173/digichat/`.
