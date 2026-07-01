---
title: DigiSmith
type: module
status: reviewed
created: 2026-04-19
tags:
  - support
  - observability
---
# DigiSmith

> Observability for the DigiThings ecosystem — tracing, metrics, and status, without the overhead.

**What it is:** DigiSmith is the observability layer for DigiThings. It provides a thin, side-effect-free wrapper around LangSmith for agent tracing and a public `/v1/status` endpoint that reports ecosystem health without leaking secrets. The Prometheus metrics helper itself lives in DigiBase (`install_metrics`); DigiSmith's role is to drive consistent adoption of that helper across services alongside tracing.

**Design principle:** DigiSmith should be invisible when working and loud when something breaks. Zero dependencies beyond FastAPI and Pydantic. LangSmith integration is optional — if not configured, tracing calls are no-ops.

**Current state:** LangSmith wrapper (optional), `/v1/status` endpoint returning public metadata, `/health` and `/healthz` liveness endpoints. No database, no background workers.

**12-month roadmap:**
- Roll the DigiBase `install_metrics` helper out to every service so each exposes a `/metrics` endpoint with consistent labels
- X-Request-ID correlation ID propagation across all services (DigiGraph, DigiSearch, DigiQuant, DigiKey, DigiClaw) — enables tracing a request through the full stack
- PII redaction middleware before any data reaches LangSmith
- Structured logging throughout (DigiSearch currently has zero structured logging)
- Grafana dashboard for operational visibility

**Open source vs. proprietary:** Entirely open. Observability infrastructure is commodity.
