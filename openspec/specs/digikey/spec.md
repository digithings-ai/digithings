# DigiKey — Spec

**Port:** 8005  
**Role:** Auth plane — RS256 JWT issuance, scoped API key management, JWKS endpoint.

## Capabilities

- RS256 JWT issuance and verification
- Scoped API key creation, validation, and revocation
- JWKS endpoint for public key distribution (`/.well-known/jwks.json`)
- Token exchange (API key → short-lived JWT)
- DigiAuthMiddleware injected into all other services

## Invariants

- **Human gate**: any change to auth, JWT, or crypto code requires human review
- RS256 only — symmetric algorithms (HS256 etc.) are forbidden
- API keys are hashed before storage; plaintext never persists
- Scopes are always validated server-side — never trust client-supplied scope claims
- `/healthz` and `/openapi.json` are auth-exempt

## Public API

| Method | Path | Description |
|--------|------|-------------|
| GET | `/.well-known/jwks.json` | Public key set |
| POST | `/v1/token` | Issue JWT for valid API key |
| POST | `/v1/keys` | Create scoped API key |
| DELETE | `/v1/keys/{id}` | Revoke API key |
| POST | `/v1/verify` | Verify a JWT inline |
| GET | `/healthz` | Liveness probe |

## Shared Middleware

`DigiAuthMiddleware` (from `digikey/src/digikey/integrations/service_middleware.py`) is the single auth layer for all services. Public paths are whitelisted; all other paths require a valid JWT with correct scope.
