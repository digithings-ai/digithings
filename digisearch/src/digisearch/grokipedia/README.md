# grokipedia (digisearch MCP spike)

Thin read-only client + MCP tools (`grokipedia_search`, `grokipedia_get_page`)
wrapping public grokipedia.com JSON APIs. No HTML scrape of `/page/{slug}`.

## Endpoints (probed 2026-10-02)

| Tool | Live URL | Notes |
|------|----------|--------|
| search | `GET https://grokipedia.com/api/full-text-search?query=&limit=` | `{results:[{slug,title,snippet,...}]}` |
| get_page | `GET https://grokipedia.com/api/page-preview?slug=` | `{found,page:{slug,title,content,...}}`. Optional `includeContent=true` or site-style `content=0` for a short preview. **`/api/page` 404s** — page-preview is the source of truth. |

## robots / ToS

`https://grokipedia.com/robots.txt` currently has `User-agent: *` / `Disallow: /api/`.
The public site JS still calls these APIs. This wrapper is unofficial/third-party,
polite (min spacing ≥300ms + token bucket), and a **spike only**. HOLD hatch for a
One/Chris legal/product call — do not attach in production from this PR.

User-Agent: `digithings-digisearch-grokipedia/0.1 (+https://github.com/digithings-ai/digithings)`.
