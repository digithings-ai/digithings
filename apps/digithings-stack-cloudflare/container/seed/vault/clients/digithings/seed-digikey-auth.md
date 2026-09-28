---
title: digikey JWT and scopes
tags: [digithings, seed, digikey, auth]
---

# digikey JWT and scopes

Auth plane: **RS256** JWTs, **JWKS** publication, BFF session exchange, and
scoped API keys (`dgk_live_…`).

Example scopes: `digisearch:query`, digivault read/write, digigraph workflow.
Browser never holds service JWTs — digichat exchanges them server-side.

Not covered here: Chroma chunking, vault wikilinks, or NautilusTrader backtests.
