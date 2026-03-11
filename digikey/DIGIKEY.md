# DigiKey – Security & Identity Foundation

**Part of [DigiThings](https://github.com/digithings-ai/digithings) (digithings.ai).**  
**Purpose** (from root `DIGI.md`): Central key‑vault, secrets management, and identity/security primitives for the entire DigiThings stack.

Unlike the other `digi*` folders, `digikey` contains no executable code yet; it
is a placeholder for the security layer that ties all components together and
ensures least‑privilege, auditable key access, and service‑to‑service
authentication.

## Design Principles

* **Zero trust by default** – every request between DigiClaw, DigiGraph,
  DigiQuant, DigiSearch, etc. must authenticate and be authorized via
  DigiKey-issued credentials or tokens. No component is implicitly trusted
  based on network location.
* **Secrets-as-code** – keys, certificates, and vault policies are defined in
  versioned YAML/JSON and deployed via CI. No plaintext secrets live in git.
* **Interoperable KMS** – DigiKey will wrap or federate with existing
  key‑management systems (HashiCorp Vault, AWS KMS, Azure Key Vault) so that
  customers can plug in their preferred provider without changing the rest of
  the stack.
* **Auditable access** – every secret request is logged (read/write/renew) with
  user/agent identity and timestamp. Logs feed into the global audit trail.
* **Fine‑grained roles** – use RBAC or OPA policies so that agents only see the
  keys they are allowed to use (e.g. DigiGraph research agents may read model
  API keys but cannot access live trading credentials held by DigiQuant).

## Core Responsibilities (phase 0 placeholder)

* Define the **secrets store schema**; keys are namespaced by project and
  environment (`digi/<component>/<purpose>`).
* Provide **token issuance and rotation** for service-to-service calls. Tokens
  are short‑lived JWTs signed by DigiKey and checked by other services via a
  shared public key.
* Expose a simple HTTP API for retrieving secrets (`GET /secrets/{name}`) and
  for leasing ephemeral credentials (e.g. database passwords).
* Integrate with the **heartbeat/audit** system: DigiClaw’s heartbeat will ping
  DigiKey regularly to validate its health and rotate its own credentials.
* Supply libraries (Python/Node) that wrap file‑based config and call the
  API transparently; e.g. `digikey.client.get_secret("digi/digiquant/db")`.
* Optionally, serve as a **signing authority** for container images, model
  artifacts, or policy documents.

## Tech Stack (tentative)

- Primary implementation planned as a lightweight Python FastAPI service.
- Storage back‑end pluggable: file system (dev), HashiCorp Vault, AWS Secrets
  Manager, or Azure Key Vault.
- Use `python-jose` or `PyJWT` for token issuance/validation.
- Policy engine: OPA/Wail for RBAC, evaluated on each request.
- CLI tool (`digikey` executable) for vault bootstrap and secret management.

## Interfaces with Other Components

| Consumer | Interaction | Purpose |
|----------|-------------|---------|
| DigiClaw | Retrieves API keys, email creds, heartbeat tokens | Gateway operations & heartbeat. |
| DigiGraph | Reads model API keys, project‑level config, MCP server
  credentials | Research & agent workflows. |
| DigiQuant | Fetches live trading credentials, broker API tokens, drift
  detection thresholds | Backtest/live execution & monitoring. |
| DigiSearch | Stores encryption keys for vector index files | Data-at-rest security. |
| CI/CD pipelines | Encrypts deployment secrets; rotates service tokens | Build/deploy time. |

In Phase 1 the API will be mocked; callers annotate secretos as
i.e. `DIGI_KEY_STORE_URL=http://localhost:8005` and use a simple file-based
stub. Phase 2 will replace the stub with a real vault service and enable
cross‑component authentication via DigiKey JWTs.

## Deployment & Development Notes

* For local development, the repository includes an **example Vault file** at
  `digikey/examples/vault.yaml` with dummy secrets. Developers can run
  `python -m digikey.stub` to start a lightweight server that reads that file.
* A pre‑commit hook checks that no secrets are accidentally committed.
* CI pipelines will require a separate series of encrypted variables (e.g.
  `DIGI_KEY_ROOT_TOKEN`) which are stored in the organisation’s secret manager.

## Roadmap (Future)

1. **Phase 1** – scaffolding and stub service, integrate with heartbeat/audit.
2. **Phase 2** – full storage back‑end, token issuance, RBAC policies, operator
   CLI.  Add support for KMS federation.
3. **Phase 3** – sign/verify service for images and models; integrate with
   GitHub Actions to automatically sign release bundles.
4. **Phase 4** – SaaS offering, multi‑tenant support, quota enforcement.

*This document is currently a placeholder; components will be added once the
security layer implementation begins.*
