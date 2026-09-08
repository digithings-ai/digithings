# ADR 0027: OpenCode as digichat CLI/TUI foundation

**Status:** superseded by [ADR-0028](0028-digichat-web-foundation-and-opencode-distribution.md)
**Date:** 2026-09-04

## Context

digichat’s primary product surface is a web BFF + `@digithings/digichat-ui` (`DigiChatSession`), oriented toward RAG / knowledge (digisearch and digivault via digigraph tools, Foundry for some client embeds). Rebuilding a first-class CLI/TUI (command palette, dismissible help, prompt overlays, streaming tool chrome) from scratch would duplicate work already solved by **OpenCode** ([anomalyco/opencode](https://github.com/anomalyco/opencode), MIT, TypeScript/Bun, OpenTUI).

Product intent is to **adapt OpenCode** for digichat CLI look and interaction, keep coding/edit capabilities as a **future feature path**, and **not** replace the web digichat surface in the near term.

Full inventory, option ranking, phases, and spike plan live in:

[`docs/architecture/opencode-digichat-adoption.md`](../architecture/opencode-digichat-adoption.md)

## Decision

**Working recommendation (pending spike):** adopt a **hybrid** path —

1. Keep web digichat (BFF + digichat-ui) as the embed/`/chat` product.
2. Add an OpenCode-based CLI for operator/power-user dogfood, configured for digithings via MCP + plugins (digigraph → digisearch / digivault).
3. Prefer config/plugin/SDK integration over an immediate hard fork; escalate to fork only if packaging blocks a branded CLI.
4. Do **not** change digikey cryptography as part of this path; reuse existing API key / token exchange.

This ADR stays **proposed** until the Phase 1 spike in the architecture doc reports go/no-go on #3568.

## Consequences

**Positive:**

- Reuses mature TUI overlays and agent UX instead of rebuilding them in digichat-ui.
- Aligns with digithings MCP-first tool design.
- Preserves web security model (BFF) and self-hosted digichat release story.
- Leaves a clear path to enable OpenCode’s code-editing agent later.

**Negative / tradeoffs:**

- Two client surfaces (web + CLI) until session parity is designed.
- Dependency on a fast-moving upstream (Bun/OpenTUI monorepo).
- Risk of dual “brains” if OpenCode’s agent loop is not subordinated to digigraph for stack tools.

## Links

- Issue: [#3568](https://github.com/digithings-ai/digithings/issues/3568)
- Architecture plan: [`docs/architecture/opencode-digichat-adoption.md`](../architecture/opencode-digichat-adoption.md)
- digichat modular frontend: [`docs/architecture/digichat-modular-frontend.md`](../architecture/digichat-modular-frontend.md)
- Superseded by: [ADR-0028](0028-digichat-web-foundation-and-opencode-distribution.md)
