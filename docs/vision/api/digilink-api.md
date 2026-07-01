---
title: "digilink — API reference"
type: reference
status: generated
created: 2026-06-29
tags:
  - api
  - roadmap
relevance:
  - digilink
---
# digilink — API reference

> A protocol bridge so non-native transports speak MCP.

**Role:** MCP protocol bridge · roadmap · **Tier:** roadmap

## Overview
Roadmap: a translation layer registering adapters that turn REST, gRPC, or bespoke transports into MCP tools.

Today MCP is built into individual modules; this keeps the stack open instead of locked to one protocol.

## Authentication
Roadmap. Today MCP is built into individual modules (e.g. digisearch-mcp).


## Notes
- Planned: a protocol bridge registering adapters that turn REST, gRPC, or bespoke transports into MCP tools.
- Planned surface: digilink.register_adapter("rest", …) to expose a non-native transport as MCP.

## Stack
MCP, HTTPx

## Related
digigraph, digiquant

## Links
- [Roadmap](https://github.com/digithings-ai)

See also [[digilink]].
