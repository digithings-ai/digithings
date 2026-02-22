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

3. **Human-in-the-Loop Gates**  
   - All irreversible actions (live order placement, email sends, fund transfers) require explicit user confirmation via DigiClaw chat  
   - Configurable via `HUMAN_GATE.md` per workspace

4. **Audit & Observability**  
   - Every MCP call, LangGraph checkpoint, and Nautilus order is logged with timestamps, agent ID, and inputs/outputs (secrets redacted)  
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
- Automatic revocation of compromised sessions via Queue Manager

**Deployment Command (Phase 3)**  
- Default (loopback-only): `docker compose up -d`
- With heartbeat monitoring: `docker compose --profile heartbeat up -d`
- All services bind to `127.0.0.1` only; use Tailscale or Cloudflare Tunnel for remote access. No public port exposure.