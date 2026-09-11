# digikey authentication (seed)

Auth plane for digithings services. Distinct from RAG or vault retrieval.

## Tokens

- **RS256** JWTs signed by digikey
- Public keys published at **JWKS**
- Browser never holds service JWTs; digichat BFF exchanges a session grant

## Scopes

Service calls require scoped bearer tokens, for example:

- `digisearch:query` / `digisearch:ingest`
- digivault read vs write scopes
- digigraph workflow scopes

## API keys

Operators can issue `dgk_live_…` API keys and exchange them via
`POST /v1/oauth/token` with `grant_type=api_key`. Dev-only `dev_global` keys need
`DIGIKEY_ALLOW_DEV_GLOBAL=1`.

## What this note does not cover

NautilusTrader backtests, Chroma chunking, or Obsidian vault frontmatter — see
the dedicated seed notes for those topics.
