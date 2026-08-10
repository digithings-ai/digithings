# digithings chat — product showcase (seed)

This note is the **canonical self-description** for digithings.ai/chat. It ships
in the Profile A stack image so digisearch index `digithings_docs` can answer
“how is this chat built?” with grounded citations before a full docs_onboard run.

Digi product names are always lowercase in prose (`digichat`, `digigraph`,
`digivault`, `digisearch`, `digikey`, `digithings`).

## One-line pitch

**digithings.ai/chat is client #0:** the same self-hosted **digichat** +
**digigraph** + **digivault** + **digisearch** stack we ship to customers — not a
separate demo product.

## What you are talking to

| Layer | Role |
|---|---|
| **digichat** | Next.js chat UI + BFF (`/embed` on digithings.ai; ungated tenant) |
| **digigraph** | LangGraph orchestration — research workflow, tool routing, LiteLLM |
| **digikey** | JWT + scoped API keys for service-to-service auth |
| **digivault** | Obsidian-style markdown notes; vault path prefix `clients/digithings/` |
| **digisearch** | Chunk, embed, index — collection `digithings_docs` for RAG retrieval |
| **digillm** | LiteLLM proxy (model routing + caching) |

Browser path:

```text
digithings.ai/chat → iframe digichat /embed → digigraph → digillm + tools
                                                      ↘ digivault_search_notes
                                                      ↘ digisearch (digithings_docs)
```

## Corpus — how answers are grounded

Offline **docs_onboard** builds the full dogfood corpus (website crawl, monorepo
docs, OpenAPI). This Profile A image also carries a **static seed** of showcase /
architecture / product notes into Chroma + digivault so chat works on first boot.

**Dual-sink:** vault notes under `clients/digithings/` and digisearch index
`digithings_docs`.

## Same product customers deploy

- Profile A self-host install (Compose + Cloudflare Containers path)
- Operator path for digithings.ai uses the same digichat + digigraph + digikey stack
- Auth on public chat: embed-only, ungated (`DIGICHAT_REQUIRE_ROOT_AUTH=0`);
  digikey still secures service APIs

## Canonical questions this note answers

- How is digithings chat built?
- What powers digithings.ai/chat?
- Is this the same product you would deploy for me?
- What is client #0 / dogfood?
- Where do vault + search get their documents?
