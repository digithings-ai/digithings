# digithings chat — product showcase (client #0)

This note is the **canonical self-description** for digithings.ai/chat. It is
ingested by `docs_onboard` into digivault (`clients/digithings/…`) and the
`digithings_docs` digisearch index so the assistant can answer “how is this chat
built?” with grounded citations.

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
| **digivault** | Notes + graph; production search via Supabase FTS when `DIGIVAULT_ROOT` unset |
| **digisearch** | Chunk, embed, index — `digithings_docs` index for RAG retrieval |
| **digillm** | LiteLLM proxy (model routing + caching) |

Browser path:

```text
digithings.ai/chat → iframe digichat /embed → digigraph → digillm + tools
                                                      ↘ digivault_search_notes
                                                      ↘ digisearch (digithings_docs)
```

## Corpus — how answers are grounded

Offline **`docs_onboard`** (`scripts/docs_onboard/run_onboard.py`) builds the
dogfood corpus from manifest
[`docs/projects/digithings/onboard.yaml`](onboard.yaml):

| Source | What gets indexed |
|---|---|
| **Website crawl** | digithings.ai + digiquant.io (marketing/docs pages; chat UI is digithings.ai only) |
| **Monorepo docs** | `ARCHITECTURE.md`, `AGENTS.md`, `docs/**`, component guides (see `sources/repo-docs.yaml`) |
| **OpenAPI** | `docs/openapi/*.json` service specs |
| **This file** | First-class showcase note at `docs/projects/digithings/SHOWCASE.md` |

**Dual-sink:** each run writes **both** digivault notes under
`clients/digithings/` and digisearch index **`digithings_docs`**. Operators
publish vault notes to Supabase `architecture_notes` via
`scripts/sync_onboard_vault.py`.

Runbook: [`docs/digichat/CLIENT-DOCS-ONBOARD.md`](../../digichat/CLIENT-DOCS-ONBOARD.md).

## Same product customers deploy

- **Profile A** self-host install: [`docs/digichat/INSTALL.md`](../../digichat/INSTALL.md),
  [`infra/digichat-release/`](../../../infra/digichat-release/).
- **Operator path (digithings.ai):**
  [`infra/digichat-digithings/README.md`](../../../infra/digichat-digithings/README.md).
- After **Stage A** (human-owned develop→main + GHCR publish), operators pull
  stock images (`ghcr.io/digithings-ai/{digikey,digigraph,digivault,…}`) instead
  of monorepo build — same artifacts clients receive.

We do **not** claim a multi-tenant SaaS control plane here; this is
**self-hosted digichat** on operator infrastructure (Docker Compose + Cloudflare
Tunnel for digithings.ai).

## Auth on the public chat

Dogfood uses **Option A — embed-only, ungated**:

- `DIGICHAT_REQUIRE_ROOT_AUTH=0` — no `/login` wall on the chat path.
- Tenant `gateMode: ungated` for `digithings.ai` embed hosts.
- **digikey** still secures service APIs (digigraph ↔ digivault/digisearch).

## digigraph project config

Point **`DIGI_PROJECT_CONFIG`** at the committed dogfood snippet:

- [`config/dogfood-digiproject.yaml`](../../../config/dogfood-digiproject.yaml)
  (operator default)
- or [`docs/projects/digithings/digiproject.yaml`](digiproject.yaml) (same shape,
  co-located with the manifest)

The `research_system_prompt` instructs the model to cite this note and related
corpus when asked how the chat or platform is built — without inventing features
not in the indexed docs.

## Future (not shipped)

**online compliance center (OCC)** may later embed under `/chat/occ` as a separate
tenant surface; that is out of scope for this showcase and not part of the current
digithings.ai/chat product.

## Canonical questions this note answers

- How is digithings chat built?
- What powers digithings.ai/chat?
- Is this the same product you would deploy for me?
- What is client #0 / dogfood?
- Where do vault + search get their documents?

## Related

- Project tree: [`docs/projects/digithings/README.md`](README.md)
- Cutover plan: [`docs/superpowers/plans/2026-08-10-digithings-dogfood-cutover.md`](../../superpowers/plans/2026-08-10-digithings-dogfood-cutover.md)
- Gap log: [`GAPLOG.md`](GAPLOG.md)
