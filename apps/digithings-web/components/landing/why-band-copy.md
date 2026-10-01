# Why-band copy deck (Refs #4429)

Single variant: three apps, one consistent digithings shape, price table
always below. Live in the landing's `#why` band — this file tracks
decisions, not the full text (the text lives in `appPresets.ts` and
`whyStory.ts`).

Framing: less you-vs-theirs, less owning-vs-renting. Custom builds,
modularity, no lock-in, price. Owning is part of it, never the headline.
digiquant stays out of the infra story except as the finance app's top box
(a product built on the stack, not a layer of it).

## The three architectures (provider side differs per app)

- RAG: full traditional stack (gateway, models, embeddings, Pinecone,
  lake, telemetry, GPUs, terms).
- Support: no vector indexing — model + email service + runner + review
  lane + telemetry + terms. Lock-in is the loop, not an index.
- Finance: reasoning + nightly runner + research archive + telemetry +
  terms; sources are scattered market endpoints.

## digithings side (one shape, all apps)

Same 8-module 4×2 every time; per app only the top box changes (product /
support agent / digiquant pipeline) plus dimming (support rests vault and
index dimmed). Any module swaps to a provider option — the boundary counts
vendors, demonstrating modularity in the drawing.

## Invoice (always below, per selected app)

Setup + monthly per side from the tested pricing; fixed $0 layers where an
app has no box (support/finance run no vector indexing). Scale story next:
scroll-scrubbed totals + exponential chart (the prisoner thesis) — queued.

## Scorecard

- [ ] Provider support email box: unnamed "email service" — name a product?
- [ ] digibase/digistore/digilink: caption + mosaic enough, or name them?
