---
title: DigiLink
type: module
status: reviewed
created: 2026-04-19
tags:
  - roadmap
  - connectors
---
# DigiLink
> Every DigiThings capability, any protocol — the connection layer that eliminates lock-in.

## What it is

DigiLink is the connection and translation layer for the entire DigiThings ecosystem. It serves two roles: standardising how modules communicate with each other internally, and translating capabilities to external protocols so clients can access them via whatever interface fits their workflow — HTTP REST, MCP tool (the protocol used by Claude Desktop, Cursor, Windsurf, and other AI apps), CLI command, or Docker container.

DigiLink is not yet implemented as a standalone module. It is designed and its specification is settled. The problem it solves is real and growing — today, each DigiThings module exposes its own REST API independently without a shared translation layer. DigiLink consolidates and standardises this. The schedule and current state are described plainly below.

## The problem it solves

Most AI platforms force a specific integration pattern: use the SDK, or use the HTTP API, or call the CLI. Switching requires rebuilding the integration. When a client wants to call a DigiQuant backtest via Claude Desktop instead of a curl command, they currently cannot — or they build the MCP adapter themselves.

DigiLink makes this a non-issue. A capability is defined once and is available through every supported protocol automatically. The integration is not rebuilt per client; it is generated from a single source of truth.

## How it fits in the ecosystem

### The core principle

No DigiThings capability is protocol-native. Every capability is defined once. DigiLink translates it to:

- **REST endpoint** — default, always present, source of truth for all capabilities
- **MCP tool definition** — enables Claude Desktop, Cursor, Windsurf, and other desktop AI apps to call DigiThings capabilities natively
- **CLI command** — scripting, automation, direct terminal use
- **Docker entrypoint** — portable deployment without additional tooling
- **Webhook / event connector** — async integrations (planned)

### Internal face

DigiThings modules communicate with each other using the same standard protocol they expose externally: HTTP REST today, gRPC for performance-critical paths in the future. No proprietary internal messaging. No custom IPC. If a module's internal interface differs from its external interface, that is a design defect, not a feature.

### External face

The protocol translation layer. A capability is added to the registry; DigiLink generates the adapters. Adding a new module does not require writing integration code for each protocol — the translation is handled centrally.

### What this means for clients

A client running Claude Desktop calls DigiQuant backtest tools via MCP. Another client running automated scripts uses the generated CLI. An enterprise integration uses the REST API. A third-party webhook triggers a DigiSearch ingestion run. Same underlying capability, zero rebuilding, no vendor lock-in.

DigiLink replaces the deferred "OpenClaw gateway" concept from the early DigiClaw roadmap. DigiClaw now focuses purely on agent orchestration and scheduled execution. DigiLink owns the connector layer.

## Capabilities — Current

**Not yet implemented as a standalone module.** This is the honest current state.

Today, individual DigiThings services expose their own REST APIs independently. DigiGraph has an MCP server. DigiClaw has an MCP skill interface. These exist and work. What does not yet exist is the unified capability registry and the automated adapter generation that DigiLink will provide — the layer that makes "add a capability once, expose it everywhere" true across the entire ecosystem rather than per-module.

The protocol translation problem is solved piecemeal today. DigiLink makes it systematic.

## Capabilities — 12-month roadmap

- **Formal DigiLink module** — capability registry, adapter framework, routing from a single source of truth
- **MCP adapter generation from OpenAPI specs** — any service with an OpenAPI schema gets an MCP tool definition automatically
- **CLI wrapper auto-generation** — REST endpoints become CLI commands without manual implementation
- **Desktop AI app connector library** — tested, documented connectors for Claude Desktop, Cursor, and Windsurf; available as a standalone installable package
- **Webhook and event connector** — async trigger support for ingestion pipelines, scheduled workflows, and third-party system integrations
- **gRPC for internal service communication** — performance-critical inter-service paths migrate from REST to gRPC while the external REST surface remains unchanged

## Open source vs. proprietary

DigiLink is entirely open (MIT/Apache). The connector framework, adapter generation tooling, and all protocol translation code are infrastructure — no proprietary components. The goal is broad adoption: the more DigiThings capabilities are accessible via the widest range of protocols, the more valuable the ecosystem is for everyone building on it.
