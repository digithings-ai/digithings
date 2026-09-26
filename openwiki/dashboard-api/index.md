# Files

- [dashboard-api Architecture](architecture.md) - Architecture of the central read-only dashboard-api Cloudflare Worker at apps/dashboard-api/ — router, fail-closed Supabase source, error envelope, provenance schema, house workspace pinning, CORS, MCP JSON-RPC surface, and shared SSOT kernel, replacing direct browser Supabase reads so dashboard surfaces become thin renderers.
- [dashboard-api Contract and Routes](contract-and-routes.md) - Complete reference for every dashboard-api route — the eight contracted specific routes returning envelope-wrapped data plus provenance, the generic GET /v1/tables allowlisted reads, common query params, retrieval_pin passthrough, and the realtime-stays-client-side rule.
- [dashboard-api Operations](operations.md) - How to develop, test, deploy, and operate the dashboard-api Cloudflare Worker — wrangler commands, secrets model, env vars, stub-vs-real lane switching, CORS configuration, CI/CD pipeline, and fail-closed failure semantics.
