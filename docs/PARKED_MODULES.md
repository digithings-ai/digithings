# Parked modules

A **parked** module is kept on `develop` but is not released.

- It stays in the repo on `develop`; CI may still test it.
- It is **excluded** from `main`, from `release/<module>/vX.Y.Z` branches and from
  per-module release checklists and version bumps.
- It gets no banner, site page or marketing until un-parked.
- Its `README.md` starts with `**Status: parked.**` and states the idea.
- It is listed below and in `agents.yml` with `status: parked`.

Un-parking is a deliberate decision by the owner: remove it from this list, then
add it to the next release plan.

## Currently parked

| Module | Since | Notes |
|---|---|---|
| digibot (formerly digiclaw) | 2026-10-11 | Future thin wrapper over OpenClaw / Hermes / Paperclip-style bot runtimes. digisearch still imports `digibot.cron`; move that grammar to a shared package before excluding digibot code from a release that ships digisearch monitors. |
