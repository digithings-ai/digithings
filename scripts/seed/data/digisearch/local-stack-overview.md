# Seed corpus — local stack overview

Synthetic document for the digithings local reference stack. It carries no
client data and no market data; every number is generated from `--seed`.

It exists so `make seed-digisearch-local` has something to ingest on a
freshly created local stack, without any network access or provider key.

## What the local stack is

- The self-host reference variant of the digithings AI infrastructure.
- One of two first-class deployment targets, alongside hosted Cloudflare.
- The pre-production gate: every surface is verified connected locally
  before anything is deployed to Cloudflare.

## What a seed is for

- Demo users and tenants, so tenancy is exercisable without a login.
- Scoped API keys, so ingest works without a production credential.
- A small public market-data slice, so chart surfaces have something to draw.
- Narrative fixtures, so document-shaped views are not empty.

Every seed value is derived from `--seed`, so two runs on two machines
produce identical bytes.

<!-- seed: 42 -->
