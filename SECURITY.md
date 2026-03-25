# Digi Security & Compliance Framework (February 20, 2026)

**Version 1.0** | **Status: Living Source of Truth**  
**Reference:** `DIGI.md` Section “The 2026 Security Crisis and Hardening Standards”

The rapid adoption of OpenClaw-based systems in early 2026 triggered the **ClawHavoc** campaign and the critical vulnerability **CVE-2026-25253** (one-click RCE via browser pivot and token exfiltration). Over 800 malicious skills were identified in the public ClawHub registry (20 % of the marketplace). **Digi** treats security as a first-class architectural concern, not an afterthought.

## Threat Model (2026 Context)
- Malicious MCP skills / skills marketplace attacks
- Remote code execution through browser automation
- Token exfiltration and lateral movement
- Data exfiltration of trading strategies or live positions
- Regulatory violations (FINRA 2026 Oversight Report, Regulation S-P amendments effective June 3 2026)

## Mandatory Hardening Standards for All Deployments
1. **Isolation**  
   - Run the DigiClaw gateway in an isolated container or VM  
   - Bind **only** to loopback interface (`127.0.0.1`)  
   - Use Tailscale or Cloudflare Tunnel for any remote access — never expose ports publicly

2. **Least Privilege**  
   - MCP tools receive only the exact permissions required (read-only data feeds, no fund-transfer rights unless explicitly approved)  
   - File-system access restricted to workspace directories via Docker volumes and AppArmor / seccomp profiles  
   - **DigiGraph** orchestrator: optional tool allowlists, opt-in debug/thread HTTP routes, and execution flags — see `digigraph/docs/SECURITY.md`  
   - **Compose defaults:** `DIGI_ENABLE_DEBUG_ENDPOINTS` and `DIGI_ENABLE_THREAD_API` default to **off** (`0`) so `/v1/debug/*`, `/test_llm`, and `/threads/*` are not exposed until you set them to `1` in `.env` (recommended for local dev only).  
   - **LiteLLM proxy:** With no `LITELLM_MASTER_KEY`, the router may accept requests without a valid Bearer (acceptable only on loopback/trusted networks). For anything beyond local dev, set **`LITELLM_MASTER_KEY`** (`sk-...`) and set **`LITELLM_PROXY_API_KEY`** on **DigiGraph** to that same master or a virtual key; keep **`OPENAI_API_KEY`** for **upstream** OpenAI routing inside the LiteLLM container, not as the DigiGraph→LiteLLM Bearer when they differ. Optional: set **`DIGIKEY_LITELLM_PROXY_KEY`** on **DigiKey** to the same value so **`POST /v1/oauth/token`** returns **`litellm_proxy_api_key`** and DigiChat can forward **`X-LiteLLM-Proxy-Key`** per request (loopback/trusted BFF only).  
   - **DigiKey JWTs:** DigiGraph, DigiQuant, and DigiSearch **require** `DIGIKEY_JWKS_URL` (or `DIGIKEY_PUBLIC_KEY_PEM`) and a Bearer JWT on non-exempt routes; there is no legacy static `DIGI_API_KEY` path and no open-by-default middleware. DigiSearch also requires a real index backend (Azure or Chroma) unless `DIGISEARCH_ALLOW_STUB=1` (tests only).

3. **Human-in-the-Loop Gates**  
   - All irreversible actions (live order placement, email sends, fund transfers) require explicit user confirmation via DigiClaw chat  
   - Configurable via `HUMAN_GATE.md` per workspace

4. **Audit & Observability**  
   - Every MCP call, LangGraph checkpoint, and Nautilus order is logged with timestamps, agent ID, and inputs/outputs (secrets redacted). Optional DigiKey trace fields (`key_prefix`, `tenant`, `project_id`, `jti`) may appear on workflow audit events when DigiGraph validates a JWT.  
   - Integration with Prometheus + Grafana (included in Docker Compose)  
   - Full execution trace exportable for FINRA/SEC review

5. **Memory & Data Protection**  
   - Graphiti / Neo4j runs inside the same isolated container  
   - Persistent strategy memory encrypted at rest (AES-256) when deployed for clients  
   - Local-first by default — no data leaves the user’s machine unless explicitly opted-in

## Regulatory Compliance (FINRA / SEC 2026)
- **Supervision & Oversight** — Full audit trail of every agent decision  
- **Best Execution** — Nautilus risk engine logs demonstrate compliance even during extended-hours trading  
- **Regulation S-P** — Written program for unauthorized access detection and recovery  
- **Policy-as-Code** — Governance rules will be defined in `digigraph/policies/` (placeholder in v0.1) and enforced at runtime

## Digi-Specific Controls
- DigiClaw heartbeat agent runs security checklist every 30–60 min  
- All MCP servers exposed by DigiQuant are read-only by default  
- **DigiClone / DigiQuant** — backtests and exports (`nautilus_bundle`, JSON configs) are **research artifacts**; paper and live execution remain behind the human-in-the-loop gates above; never enable broker keys in shared export bundles.  
- Automatic revocation of compromised sessions via Queue Manager

## Research corpora & publication rights

- **Tier-tagged evidence** (peer-reviewed, working papers, web) in DigiSearch must respect copyright and license: index metadata and allowed full text only; see `digisearch/DIGISEARCH.md` and `digigraph/docs/SECURITY.md`. Do not automate retrieval of paywalled PDFs without entitlement.
- **EDGAR dev sample** — Optional local index `edgar_dev` is built from public SEC filings via the [**EDGAR-CORPUS**](https://huggingface.co/datasets/eloukas/edgar-corpus) dataset (Loukas et al., ECONLP 2021). Use only for **dev/testing** on loopback; keep slice sizes small; cite the corpus when publishing results derived from it.

## Audit durability and edge exposure

- **Remote audit mirror** — `digiclaw` (and components using the same JSONL schema) may POST copies of audit lines to **`AUDIT_SINK_URL`** (NDJSON-friendly HTTPS endpoint). Local JSONL remains authoritative for the node; the sink is best-effort and must not receive secrets (redact before append).
- **Edge gateway** — Position **DigiClaw** (or a dedicated API gateway) as the **only** Internet-facing surface: OIDC or mTLS, session binding, and global rate limits. Keep **DigiGraph** and quant/search APIs on loopback or private networks behind that edge, consistent with the loopback-first defaults in this document.

**Deployment Command (Phase 3)**  
- Default (loopback-only): `docker compose up -d`
- With heartbeat monitoring: `docker compose --profile heartbeat up -d`
- All services bind to `127.0.0.1` only; use Tailscale or Cloudflare Tunnel for remote access. No public port exposure.