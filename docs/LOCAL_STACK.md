# Local full stack (digikey + services + LiteLLM + digichat)

**This file has moved.** The content is now part of [SELF_HOST.md](SELF_HOST.md), the reference document for self-hosting digithings: modular Compose profiles, macOS and Linux, licence notes, authentication scopes, data seeding, health checks and parity with the hosted Cloudflare variant.

In short: run the backend with `make up` (Docker Compose, the recommended path) or `make stack-local` (host processes, no Docker); both use ports 4000 and 8000–8005 with JWT auth issued by digikey on 8005. That is the whole of it — everything else, including what the self-host plan adds later, is in the linked document.

This stub is kept because the repository, its Makefile, its deployment notes and its 2026-06 audit records all link here by name. It will be removed once those links are updated by the slices that own those files.
