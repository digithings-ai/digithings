# digithings.ai/chat — FAQ (seed)

## What is this chat?

Public documentation assistant for digithings. **Client #0 dogfood** of the
self-host chat path.

## Why do I see Sources?

Answers are grounded. digigraph prefetches digisearch and digivault before
writing a reply. Cite the returned paths.

## Is OCC the same chat?

**Online Compliance Center** is a separate embed tenant (`/chat/occ`) with corpus
`occ_help` and vault prefix `clients/online-compliance-center/`. Default
digithings.ai/chat does not load OCC policies.

## Can I bring my own API key?

When the tenant enables BYOK, digichat may use a session-only provider key for
generation. Service auth still goes through digikey.

## Where does the corpus come from?

1. Stack image seeds (these markdown files) — first-boot grounding
2. `docs_onboard` — full website crawl + monorepo docs + OpenAPI (operator path)
