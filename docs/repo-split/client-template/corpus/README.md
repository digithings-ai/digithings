# corpus

Crawled public pages, one markdown file per page, each with front matter:

```
---
url: https://example.com/about
title: About
fetched: YYYY-MM-DD
---
```

`corpus/<corpus-id>/` is uploaded to R2 by the deploy and read by the stack at
boot. `manifest.json` lists every page and its source URL. The crawl script lives
next to this file once the client has one.
