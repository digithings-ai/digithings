---
title: DigiKey
type: module
status: reviewed
created: 2026-04-19
tags:
  - support
  - auth
relevance:
  - digigraph
  - digiquant
  - digisearch
  - digivault
---
# DigiKey

> The auth control plane — API keys, JWT issuance, SSO federation, and access scope enforcement for the entire ecosystem.

**What it is:** DigiKey is the single authentication and authorization control plane for all DigiThings services. Every user, every API call, every sub-graph invocation is gated by a DigiKey-issued JWT. It manages the full identity lifecycle: issuing credentials, federating corporate SSO identities, assigning organization and project membership, and encoding fine-grained access scopes that downstream services enforce.

**The problem:** In multi-service architectures, auth is typically bolted on per-service and inconsistently enforced. DigiKey makes auth a first-class concern: one control plane, all services validate the same tokens via JWKS, and access decisions are encoded in the token itself — not scattered across service-specific configurations.

**Current state (shipped):**
RS256 JWT issuance with JWKS endpoint, API key management (dgk_live_ prefix, bcrypt hash), token exchange (api_key and bff_session grant types), scope enforcement with wildcard matching, admin key issuance. Downstream services verify JWTs locally via cached JWKS — DigiKey is off the hot path after initial exchange.

**Three major additions in roadmap:**

1. SSO identity federation:
Microsoft OIDC/SAML, Google OIDC, AWS SSO, and other enterprise identity providers. Pattern: user authenticates via corporate SSO → DigiKey maps identity to DigiThings project/organization → issues JWT with appropriate scopes. This is how a client company's employee logs in with their existing corporate credentials and gets exactly the DigiThings access their organization has provisioned for them.

2. Organization and project membership model:
DigiKey maintains a user → organization → project → access tier mapping. One DigiThings deployment can serve multiple client organizations without cross-contamination. A user's JWT contains their org ID and project ID — downstream services use this to filter data and tool access to only what belongs to their organization.

3. Resource-level access in JWTs:
Beyond service-level scopes (e.g. digisearch:read), JWTs will carry resource-level permissions — which specific DigiSearch indexes, which sub-graphs, what data filter rules apply. DigiSearch reads these to return only authorized results from a shared index. This enables one index to serve multiple users at different access levels without separate deployments.

**Enterprise client pattern:**
Client employees authenticate via Microsoft SSO → DigiKey identifies them → maps to their client project → issues JWT with index:client-project and appropriate tool scopes → DigiChat surfaces only their organization's indexes and tools → DigiSearch filters results by their access level. Zero code changes per client — configuration only.

**12-month roadmap:**
- Microsoft OIDC/SAML integration
- Google OIDC integration
- Organization + project membership API
- Resource-level JWT claims
- JWT revocation via a `jti` blocklist in Redis
- Scheduled JWKS rotation with overlap windows for zero-downtime key rollover

**Open source vs. proprietary:** Entirely open. Auth infrastructure is commodity — the value is in how it's integrated with the rest of the ecosystem.
