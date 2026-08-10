# digithings products (seed)

Short glossary for digithings.ai/chat dogfood answers.

## digichat

Next.js chat UI and BFF. Embeds on digithings.ai/chat via `/embed`. Streams
answers from digigraph; shows activity / Sources for tool calls (digisearch,
digivault).

## digigraph

LangGraph “brain”. OpenAI-compatible chat + workflow endpoints. Routes tools,
runs research_rag, calls LiteLLM for generation.

## digikey

Auth plane: RS256 JWTs, JWKS, API keys, BFF session exchange. All backend
service calls require scoped tokens (e.g. `digisearch:query`, digivault scopes).

## digisearch

RAG service. Ingests markdown/docs into named Chroma indexes, hybrid query.
Website digithings tenant uses index **`digithings_docs`**. OCC tenant uses
**`occ_help`**.

## digivault

Markdown vault (Obsidian-style). Notes live under client prefixes such as
`clients/digithings/`. digigraph tool `digivault_search_notes` full-text
searches the configured prefix.

## digillm / LiteLLM

Model proxy with caching. digigraph does not call providers directly in Profile A;
it talks to the local LiteLLM port.

## digiquant / digismith / digiclaw

Other digithings modules (quant backtest, observability, heartbeat). **Not**
part of the Profile A website-chat Container — do not claim they run inside
digithings.ai/chat unless a retrieved source says so.
