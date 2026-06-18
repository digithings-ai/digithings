# ADR 0003: Observability Baseline — Prometheus + Grafana

**Status:** proposed
**Date:** 2026-04-18

## Context

DigiThings currently ships tracing-first observability through **DigiSmith**: every FastAPI service emits structured spans carrying `workflow_id`, `request_id`, and `session_id`, and each exposes a public, secret-free `/v1/status` endpoint (per the convention in [AGENTS.md](../../AGENTS.md)). This is sufficient to reconstruct *what* happened during a workflow run, but it leaves three gaps:

1. **No metrics.** There is no way to answer "how many workflows ran in the last hour", "what is the p95 latency of `/workflow`", or "how often did LiteLLM calls fail" without replaying raw traces or tailing logs. Tracing is sampled and verbose; aggregate counters and histograms are not.
2. **No dashboards.** Operators have no shared visual surface for service health. Each on-call incident starts from `docker logs` and ad-hoc `curl` against `/v1/status`.
3. **No alerting.** Without a metrics backend there is nothing to alert *on*. Failures are discovered by users, not by the stack.

The stack is deployed via docker-compose (`make up`) for development and self-hosted pilots; a full managed observability suite (Datadog, New Relic) would be disproportionate and non-OSS. We want a baseline that is cheap, OSS, container-native, and complementary to — not a replacement for — DigiSmith tracing.

See also: [docs/VISION.md](../VISION.md) (open-core, self-hostable stack).

## Decision

Adopt **Prometheus + Grafana** as the metrics baseline, embedded in the existing docker-compose deployment.

### Instrumentation

- Add `prometheus-client` as a dependency of **digibase** (shared HTTP/audit library). digibase already owns cross-cutting concerns (audit, redaction); metrics registration belongs in the same place so every service picks it up uniformly.
- digibase exposes a small helper that:
  - Registers a default `CollectorRegistry` with process, GC, and Python runtime collectors.
  - Mounts a `/metrics` route on a FastAPI app (`text/plain; version=0.0.4`).
  - Ships default counters/histograms for HTTP request count, in-flight requests, and request duration, labelled by `method`, `route`, `status`.
- Each FastAPI service calls the helper at startup:
  - **digigraph** — `:8000/metrics`
  - **digiquant** — `:8001/metrics`
  - **digisearch** — `:8002/metrics`
  - **digismith** — `:8003/metrics`
  - **digikey** — `:8005/metrics`
- `/metrics` is bound to the same loopback-only interface as every other management endpoint. It is *not* exposed publicly and carries no secrets (route labels are normalised; high-cardinality path params are collapsed).

### Scrape + visualisation

- Add two services to `docker-compose.yml` behind a new `observability` profile (so it does not run by default for unrelated work):
  - `prometheus:9090` — scrape config targets the five service `/metrics` endpoints on the compose network every 15 s, retention 15 d.
  - `grafana:3001` — provisioned with Prometheus as a default datasource and a seed dashboard.
- Ship configuration in-repo:
  - `docs/ops/prometheus/prometheus.yml` — scrape config.
  - `docs/ops/grafana/digithings-overview.json` — seed dashboard (per-service request rate, error rate, p50/p95/p99 latency, in-flight requests, process memory).
  - `docs/ops/grafana/provisioning/` — datasource + dashboard provisioning YAML.
- A new Make target (`make up-observability`) starts the core stack plus the observability profile.

### Out of scope (this ADR)

- **Alertmanager, alert rules, and paging integrations** are deferred to a follow-up ADR once we have baseline dashboards and a feel for realistic thresholds.
- **Log aggregation** (Loki, ELK) is deferred. Audit JSONL and `docker logs` remain the log surface for now.
- **Business metrics** (workflows per tenant, LLM spend) beyond the default HTTP instrumentation will land component-by-component in follow-up issues; this ADR only commits to the plumbing.

## Consequences

**Positive**
- Operators get a shared, always-on view of stack health without standing up external SaaS.
- `/metrics` is a widely-understood contract; any future Kubernetes deployment can scrape the same endpoints with a `ServiceMonitor`.
- Centralising instrumentation in digibase prevents per-service drift and keeps label cardinality controlled in one place.
- Complements DigiSmith: metrics show *that* latency spiked; traces show *why*. Both carry `request_id` so operators can pivot between them.

**Negative / tradeoffs**
- New runtime dependency (`prometheus-client`) across every service. Small, pure-Python, MIT-licensed — acceptable.
- Two new compose services (`prometheus`, `grafana`). Extra RAM and disk for local dev; mitigated by putting them behind a profile.
- Grafana dashboard JSON is notoriously churny in diffs; we keep only a single curated seed dashboard in-repo and treat ad-hoc dashboards as disposable.
- Prometheus storage is local to the container. Long-term retention and HA are explicitly not addressed here — pilots that need it will add remote-write in a later ADR.

## Alternatives considered

1. **OpenTelemetry metrics only (no Prometheus).** Attractive because DigiSmith is trace-first and OTel unifies signals. Rejected for now: the OTel metrics ecosystem for Python is less mature than `prometheus-client`, operators have to run an OTel collector *and* a backend anyway, and the Prometheus exposition format is the de-facto lingua franca. We can layer OTel on later without discarding this baseline.
2. **Datadog / New Relic / Grafana Cloud managed.** Best UX, least ops work. Rejected: not OSS, per-host pricing is incompatible with an open-core stack users can self-host, and we would still need an on-prem fallback.
3. **Skip metrics, rely on traces + logs.** Cheapest. Rejected: without aggregate counters and histograms the team is operationally blind, and tracing backends are not designed to answer quantitative questions at scale.
4. **Push-based metrics (StatsD / Prometheus Pushgateway).** Rejected for long-lived services; pull is simpler, healthier, and matches FastAPI's request lifecycle. Pushgateway remains an option later for batch jobs (e.g., backtest workers) if needed.

## Rollout

**Phase A — plumbing**
- Land `prometheus-client` in digibase with the FastAPI helper and unit tests.
- Wire `/metrics` into each service (five small PRs, one per component).

**Phase B — compose + dashboards**
- Add `prometheus` and `grafana` services behind the `observability` profile.
- Commit seed dashboard JSON and provisioning config.
- Document the workflow in each component's `ARCHITECTURE.md` where relevant.

**Phase C — follow-ups (separate ADRs / issues)**
- Alertmanager + alert rules.
- Business metrics per component.
- Remote-write / long-term storage for production pilots.

## Links

- Related: ADR-0001 (Project Spec)
- Related: ADR-0002 (Domain Unification)
- Convention: [AGENTS.md](../../AGENTS.md) — `/v1/status` + loopback binding
- Strategy: [docs/VISION.md](../VISION.md)
- DigiSmith tracing: `digismith/`
