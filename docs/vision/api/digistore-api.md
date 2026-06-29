---
title: "digistore — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - roadmap
relevance:
  - digistore
---
# digistore — API reference

> One storage API over S3, MinIO, Postgres, or SQLite.

**Role:** Storage abstraction · roadmap · **Tier:** roadmap

## Overview
Roadmap: a storage abstraction so business code never binds to a backend, today a session-scoped dataset manager living inside digigraph.

Run SQLite on a laptop, then swap to S3 and Postgres in production without rewriting.

## Authentication
Roadmap. Today a session-scoped dataset manager lives inside digigraph; the standalone storage service is planned.


## Notes
- Planned: one storage API over S3, MinIO, Postgres, or SQLite so business code never binds to a backend.
- Planned surface: DigiStore.configure(backend=…) + get/put/list over a backend-neutral interface.

## Stack
Postgres, SQLite, S3, MinIO

## Related
digiquant, digisearch

## Links
- [Roadmap](https://github.com/digithings-ai)

See also [[digistore]].
