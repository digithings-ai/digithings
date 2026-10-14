# digibot (parked)

**Status: parked.** Formerly `digiclaw`. Lives on `develop` only; excluded from
`main`, release branches and per-module release checklists until it is built
out. See [docs/PARKED_MODULES.md](../docs/PARKED_MODULES.md).

## Idea (future, not a priority)

A thin wrapper over existing open-source "bot army" runtimes (OpenClaw, Hermes,
Paperclip or similar) that makes them easy to deploy on the digithings stack,
with integrations into digisearch, digillm and digigraph.

## What is here today

A small heartbeat runner, cron scheduler and JSONL audit log (~1.2k lines)
inherited from digiclaw. Note: digisearch monitors import the cron grammar from
`digibot.cron`, and the local stack runs the `digibot` scheduler container for
web-watch ticks. Until that grammar moves to a shared package, the scheduler
pieces stay usable; parking only stops digibot shipping as its own product.
