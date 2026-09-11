import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@digithings/web";
import { DtFooter } from "@/components/DtFooter";
import { Mono, PageHead, RuledList, RuledRow } from "../_company/prose";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "security — controls, and the limits we publish",
  description:
    "How digithings handles identity, correlation, audit and secrets: RS256 JWTs and scoped API " +
    "keys in digikey, a request id on every hop, a redacted JSONL audit trail, gitleaks and " +
    "pip-audit in CI — plus the boundaries we have not closed yet.",
};

// /security — written against the code, not against the brochure.
//
// Source of record is the root SECURITY.md (threat model + STRIDE table +
// non-negotiable defaults). Every control below was re-read in the source
// before being described here, and two statements on this page deliberately
// differ from prose elsewhere on the site because the code says otherwise:
//
//  1. Audit redaction. digibase/src/digibase/audit.py matches secret *key
//     names* — the four substrings "password", "api_key", "token", "secret",
//     recursively over a mapping. It is not a PII detector and it does not
//     inspect values. Describing it as "PII redaction" would overstate it, so
//     this page states what redact_mapping() actually does. Note also that
//     digibase.audit is ONLY that function — 38 lines, no file I/O. The JSONL
//     writer is audit_log() in digigraph/src/digigraph/audit.py and in the
//     digiclaw and digiquant copies of the same module. On a page telling
//     readers to open the source, naming digibase.audit as the writer would
//     send them to the one file that does not contain it.
//  2. Revocation. SECURITY.md still lists JWT revocation as a roadmap item,
//     but the Redis-backed jti blocklist landed (ADR-0007) and
//     digikey/integrations/service_middleware.py checks it. It is opt-in:
//     with DIGIKEY_BLOCKLIST_REDIS_URL unset, is_blocked() returns False and
//     revocation only takes effect at token expiry. Both halves are stated.
//
// The limits section is not a hedge — it is a SELECTION from the residual-risk
// column of SECURITY.md's STRIDE table, published deliberately. The table has
// eighteen rows and LIMITS below has twelve, so the page says "a selection"
// rather than claiming to reproduce the column: asserting completeness while
// dropping rows is the same defect as overclaiming a control. If you add a row
// to the STRIDE table, decide deliberately whether it belongs here.
//
// One residual risk gets stated TWICE on purpose: the absence of any Node
// dependency audit appears in PIPELINE as well as in LIMITS, because the
// pipeline section is where a reader forms the belief that dependency auditing
// is a merge gate, and a correction four sections later does not reach them.

// The identity layer — digikey (digikey/src, 18 modules).
const IDENTITY: { term: string; body: string }[] = [
  {
    term: "RS256, with a kid",
    body:
      "Access tokens are asymmetric RS256 JWTs signed with a rotating RSA key and stamped with a " +
      "kid header. Verifiers fetch the public half from the JWKS endpoint and never hold signing " +
      "material, so a compromised consumer cannot mint tokens.",
  },
  {
    term: "Scoped API keys",
    body:
      "Keys are bcrypt-hashed at rest; only a short lookup prefix is stored in the clear. Each key " +
      "carries a tenant slug and an explicit scope list, and scope matching supports component " +
      "wildcards (digisearch:*) so a key can be issued narrow and stay narrow.",
  },
  {
    term: "Scope checked per route",
    body:
      "Protected routes declare the scope they need and the shared service middleware enforces it. " +
      "When auth is not configured the middleware fails closed — a protected route returns 503 " +
      "rather than serving unauthenticated traffic.",
  },
  {
    term: "Revocation, when you wire it",
    body:
      "Revoking a key marks it revoked and pushes its live token ids to a Redis jti blocklist that " +
      "the auth middleware checks on every request; a Redis outage returns 503 rather than " +
      "failing open. With no Redis URL configured the blocklist is a no-op and already-issued " +
      "tokens stay valid until they expire — keep TTLs short if you run it that way. One " +
      "disagreement to flag before you find it yourself: SECURITY.md's revocation section predates " +
      "the blocklist and still calls revocation a roadmap item. This description is the one that " +
      "matches the code.",
  },
  {
    term: "Brute force costs something",
    body:
      "Key issuance and token mint sit behind a per-IP token bucket — 10 requests a minute, burst " +
      "20 — returning 429 with a Retry-After. Liveness and JWKS routes are exempt so probes stay " +
      "up under load. The bucket is in-process only.",
  },
];

// Everything that makes a run reconstructable after the fact.
const TRACEABILITY: { term: string; body: string }[] = [
  {
    term: "digibase.http",
    body:
      "One correlation middleware, installed by all six FastAPI services. It reads X-Request-ID " +
      "from the request or generates a uuid4, publishes it on a ContextVar, injects it onto every " +
      "log record, forwards it on outbound service-to-service calls, and echoes it on the " +
      "response header. One id, one run, end to end.",
  },
  {
    term: "audit_log(), per service",
    body:
      "Workflow events append to a JSONL audit log — timestamp, event type, agent id, payload, " +
      "with optional key prefix, tenant and jti. The writer is audit_log() in digigraph.audit, and " +
      "in the digiclaw and digiquant copies of the same module; digibase.audit is not the writer, " +
      "it supplies the redact_mapping() every writer passes its payload through. The file lives on " +
      "your host.",
  },
  {
    term: "Bounded outbound HTTP",
    body:
      "Service-to-service calls are constructed through the shared client helpers, which apply a " +
      "connect-5 / read-30 / write-10 / pool-5 second timeout envelope. A bare httpx client has " +
      "no read timeout and will hang forever against a stalled upstream, so it is banned in " +
      "production paths.",
  },
  {
    term: "No wildcard CORS",
    body:
      "Every service installs CORS from one helper that reads an explicit origin allowlist from " +
      "the environment. There is no * default: unset means the allowlist is empty and no " +
      "cross-origin script can call the service.",
  },
];

// Supply chain and repository hygiene, as wired in .github/workflows.
const PIPELINE: { term: string; body: string }[] = [
  {
    term: "gitleaks",
    body:
      "Scans the diff on every code pull request, and the full history on every push to develop and " +
      "main — the push job is literally named \"Scan (full history)\" and passes no --log-opts, so it " +
      "is a wider scan than the pull-request one, not a narrower. Any finding fails the job. The scanner is the OSS CLI at a pinned version, verified " +
      "against a recorded SHA-256 of the release tarball before it runs. Allowlist entries in " +
      ".gitleaks.toml require a written justification. Markdown-only pull requests skip this scan.",
  },
  {
    term: "pip-audit",
    body:
      "Seven Python components — digibase, digigraph, digiquant, digisearch, digismith, digikey and " +
      "digiclaw — have their locked dependency closure exported and audited against the OSV " +
      "database weekly, and whenever a change to a dependency manifest lands. HIGH and " +
      "CRITICAL findings block the merge; MEDIUM and LOW are warn-only annotations. Accepting a " +
      "CVE requires an entry with a rationale and a re-evaluation trigger. Three boundaries on " +
      "that. The workspace has eleven members, so digifetch, digillm, digiskills and digivault are " +
      "outside the matrix and their dependencies are not audited. A pull request that adds Python " +
      "code without touching a manifest does not trigger the audit at all. And the scope is Python " +
      "only — there is no Node or JavaScript dependency audit in CI, so the frontend and digichat " +
      "dependency trees are unaudited.",
  },
  {
    term: "Loopback by default",
    body:
      "Every service binds 127.0.0.1 in docker-compose.yml. Opening a port or binding 0.0.0.0 " +
      "requires a matching change to SECURITY.md and is scored against the security rubric.",
  },
  {
    term: "Debug surfaces off",
    body:
      "Debug and thread endpoints are behind environment flags that default to 0, so /v1/debug/*, " +
      "/test_llm and /threads/* are not reachable unless someone deliberately turns them on.",
  },
];

// The residual-risk column of SECURITY.md's STRIDE table. Published on purpose.
const LIMITS: { term: string; body: string }[] = [
  {
    term: "Not built for the open internet",
    body:
      "The design target is a single host or a private network. Putting these services on a " +
      "public endpoint without a hardened gateway in front is outside the threat model — reach " +
      "the stack over a VPN or a tunnel, not a public port.",
  },
  {
    term: "Redaction matches names, not values",
    body:
      "The audit redactor walks a payload and replaces any key whose name contains password, " +
      "api_key, token or secret. It does not inspect values, so it is not a PII scrubber and it " +
      "will not catch a secret stored under an unexpected key name. Keeping prompts and document " +
      "bodies out of audit payloads is a discipline enforced by review, not by the function.",
  },
  {
    term: "The live-trading gate is not a runtime interlock",
    body:
      "Broker adapters for Interactive Brokers, Alpaca and QuantConnect exist only as stubs whose " +
      "connect and submit_order methods raise NotImplementedError. What guards them is a " +
      "source-tree fact plus process: a local pre-push hook demands a human co-sign trailer on " +
      "commits touching live-trading paths, and the security rubric scores it. There is no " +
      "circuit breaker in the running system, and a hook that runs on a developer's machine can " +
      "be bypassed — after which the change still has to clear review and branch protection.",
  },
  {
    term: "Key-scope isolation, not storage isolation",
    body:
      "On a shared deployment, tenant separation is enforced at the digikey key-scope layer. " +
      "Storage-layer isolation and per-tenant resource quotas are not implemented; multi-tenant " +
      "operation is a roadmap item, not a shipped guarantee.",
  },
  {
    term: "Retrieved documents are not a trust boundary yet",
    body:
      "Tool boundaries are typed and the MCP tool set is an allowlist, which limits what an agent " +
      "can do. There is no content-level sanitiser or trust-tier tagging on documents pulled back " +
      "from retrieval, so prompt injection carried in indexed content is not systematically " +
      "defended. There is also no runtime egress allowlist on production service traffic.",
  },
  {
    term: "The audit log is local and unsigned",
    body:
      "Audit events are per-host JSONL. There is no append-only remote sink and no signed hash " +
      "chain, so the trail is evidence of what the system recorded, not tamper-proof evidence " +
      "that the record was never altered.",
  },
  {
    term: "Rate limiting does not span instances",
    body:
      "The token bucket is per-process, with no shared store, so it does not coordinate across " +
      "replicas. There are no per-key or per-tenant quotas on orchestration or retrieval paths, " +
      "and no request body-size cap at the ASGI layer — that is delegated to an upstream gateway.",
  },
  {
    term: "JWKS is cached for 300 seconds",
    body:
      "Verifiers cache the JWKS document for five minutes, so a signing-key rotation takes up to " +
      "that long to propagate to every verifier.",
  },
  {
    term: "Dependency auditing stops at Python",
    body:
      "There is no Node or JavaScript dependency audit anywhere in CI, so the frontend and digichat " +
      "dependency trees are not scanned for CVEs at all — it is written down as a follow-up, not " +
      "shipped. On the Python side, MEDIUM and LOW findings are warn-only, and a pull request that " +
      "adds code without touching a dependency manifest does not trigger the audit.",
  },
  {
    term: "Not every Action is pinned to a SHA",
    body:
      "The secret scanner is the OSS CLI at a pinned version, verified against a recorded SHA-256 " +
      "before it runs. The GitHub Actions around it are weaker: some are pinned to a commit SHA, " +
      "most only to a major-version tag, which a compromised upstream release can move under us. " +
      "Pinning is audited when a workflow file changes rather than enforced by a check.",
  },
  {
    term: "The insider controls are process, not enforcement",
    body:
      "The hooks that block protected-path edits and unsigned live-trading pushes run in the " +
      "developer's own environment, so a determined insider with write access can bypass the " +
      "harness. What is left is pull-request review and GitHub branch protection — configuration " +
      "audited out of band, not a property of the repository you can read. The same applies to the " +
      "secret-scanner allowlist: a wrongly scoped entry would mask a real leak, and only review " +
      "catches that.",
  },
  {
    term: "The public endpoints still fingerprint",
    body:
      "Liveness and JWKS are deliberately minimal and secret-free, but their response shape still " +
      "leaks stack and version information. That is accepted rather than mitigated, on the basis " +
      "that the contract is public by design — and there is no WAF or bot-management layer in front " +
      "of any of it.",
  },
];

export default function SecurityPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// security"}
          title={
            <>
              Controls, <em>and their edges.</em>
            </>
          }
        >
          Every claim below was read out of the source before it was written down, and the last
          section is the part most pages leave out: what is not covered. The full threat model,
          including a STRIDE table with a residual-risk column for each row, lives in{" "}
          <Mono>SECURITY.md</Mono> at the root of the repository — public, like the rest of it.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// identity"}</span>
              <h2>One service owns auth.</h2>
              <p>
                digikey issues and verifies everything. It is eighteen Python modules, not a
                framework plugin, and there is no static shared-secret fallback left in the stack.
              </p>
            </Reveal>
            <RuledList>
              {IDENTITY.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// traceability"}</span>
              <h2>A request you can follow.</h2>
              <p>
                The reason to run your own infrastructure is to be able to answer what happened.
                These four are the mechanics of that answer.
              </p>
            </Reveal>
            <RuledList>
              {TRACEABILITY.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// pipeline"}</span>
              <h2>What CI refuses to merge.</h2>
              <p>
                Secrets scanning and dependency auditing are gates rather than dashboards — when they
                run they fail the job instead of filing a note for later. Each row says what triggers
                it, because a gate that does not fire is not a gate.
              </p>
            </Reveal>
            <RuledList>
              {PIPELINE.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// limits"}</span>
              <h2>What we have not closed.</h2>
              <p>
                A selection from the residual-risk column of the threat model — the entries a reader
                deciding whether to deploy this would want first, not the whole table. SECURITY.md
                carries every row, each next to the mitigation it sits behind. If any of this is
                disqualifying for your deployment, better to learn it here than after an integration.
              </p>
            </Reveal>
            <RuledList>
              {LIMITS.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// disclosure"}</span>
              <h2>Reporting a vulnerability.</h2>
              <p>
                Please do not open a public issue. Email the address published in{" "}
                <Mono>SECURITY.md</Mono> with <Mono>[digithings Security]</Mono> in the subject, and
                include reproduction steps, the affected components, and any impact you know of.
              </p>
            </Reveal>
            <div className="max-w-[64ch]">
              <p className="text-[0.95rem] leading-[1.7] text-ink-soft">
                The commitment in that document is an acknowledgement within 72 hours and a
                coordinated-disclosure timeline within seven days. We will agree an embargo where
                it makes sense, and credit you in the release notes if you want it.
              </p>
              <p className="mt-[1.2rem] font-mono text-[0.88rem] text-ink-mute">
                <a
                  className="text-accent [text-underline-offset:2px] hover:text-ink"
                  href="https://github.com/digithings-ai/digithings/blob/main/SECURITY.md"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  SECURITY.md — threat model, defaults, disclosure contact
                </a>
              </p>
              <p className="mt-[1.6rem] text-[0.95rem] leading-[1.7] text-ink-soft">
                For how the same posture is enforced on the way in — the review gates, the test
                suite, the rubrics —{" "}
                <Link
                  className="text-accent [text-underline-offset:2px] hover:text-ink"
                  href="/quality"
                >
                  see the quality page
                </Link>
                .
              </p>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
