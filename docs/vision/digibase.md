# DigiBase

> Shared infrastructure library — the utilities every DigiThings service uses, kept minimal and dependency-free.

**What it is:** DigiBase is a shared Python library that provides the common infrastructure patterns every DigiThings service needs: standardized error envelopes, outbound HTTP correlation headers, audit log redaction, optional OpenTelemetry wiring. It is imported as a library — not deployed as a service.

**Design principle:** Side-effect-free on import. Zero runtime dependencies beyond the optional extras. If DigiBase grows into a service, something has gone wrong in the architecture.

**Scope clarification:** DigiBase is intentionally minimal. The "data-plane broker" role (managing Postgres/Redis credentials per tenant) that was discussed in earlier roadmap versions is now owned by DigiStore. DigiBase stays a library.

**Current state:** v0.1 shipped. 7 source files: error envelopes, outbound HTTP headers, audit redaction, Prometheus metrics instrumentation, optional OTel wiring. Fully tested.

**12-month roadmap:** Extend OTel wiring as other modules adopt it. Add shared HTTP patterns as they emerge from other module development. Resist scope expansion — keep it a library.

**Open source vs. proprietary:** Entirely open.
