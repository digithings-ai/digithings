# Parked modules

A **parked** module is kept on `develop` but is not released.

- It stays in the repo on `develop`; CI may still test it.
- It is **excluded** from `main`, from `release/<module>/vX.Y.Z` branches and from
  per-module release checklists and version bumps.
- It gets no **new** banner, site page or marketing until un-parked. A rename
  carries the existing entries forward: the banner definition, the site module
  entry, the API catalogue entry and the version-ledger row keep the module
  visible under its new name.
- The deployed image still builds and installs a parked module's wheel while
  another shipped module imports it, because the stack image would not build
  without it. `digibot` is in that state: `digisearch` still imports
  `digibot.cron`, so the wheel ships until that grammar moves to `digibase`.
- Its `README.md` starts with `**Status: parked.**` and states the idea.
- It is listed below and in `agents.yml` with `status: parked`.

Un-parking is a deliberate decision by the owner: remove it from this list, then
add it to the next release plan.

## Currently parked

| Module | Since | Notes |
|---|---|---|
| digibot (formerly digiclaw) | 2026-10-11 | Future thin wrapper over OpenClaw / Hermes / Paperclip-style bot runtimes. digisearch still imports `digibot.cron`; move that grammar to a shared package before excluding digibot code from a release that ships digisearch monitors. |
