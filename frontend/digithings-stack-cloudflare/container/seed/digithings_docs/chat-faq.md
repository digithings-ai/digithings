# digithings.ai/chat — FAQ (seed)

## What is this chat?

The public documentation assistant for digithings. It is **client #0 dogfood**:
the same digichat + digigraph stack customers can self-host.

## Why do I see Sources / digisearch / digivault?

Every answer is grounded. digigraph prefetches digisearch (`digithings_docs`)
and digivault notes under `clients/digithings/` before writing a reply. Cite
those paths when explaining how the product works.

## Is OCC the same chat?

**Online Compliance Center** is a separate embed tenant (`/chat/occ`) with its
own corpus (`occ_help` + `clients/online-compliance-center/`). digithings.ai/chat
(default) uses digithings docs, not OCC policies.

## Can I bring my own API key?

When the tenant enables BYOK, digichat can use a session-only provider key for
generation. Service auth to digigraph still goes through digikey.

## Where does the corpus come from?

1. **Stack image seeds** (this file and siblings) — first-boot grounding
2. **docs_onboard** — full website crawl + monorepo docs + OpenAPI into vault +
   digisearch (operator / CI path)
