# Files

- [digitrace Architecture](architecture.md) - Module map and design of digitrace — conditional LangSmith tracing library plus a stateless status HTTP service.
- [Status API and Operations](status-api-and-operations.md) - digitrace HTTP surface and operations — health probes, secret-free status, metrics, middleware, env vars, and container wiring.
- [Tracing and Redaction](tracing-and-redaction.md) - How digitrace traceable() activates, what tracing_enabled() reports, and how PiiRedactor scrubs span payloads before LangSmith submission.
