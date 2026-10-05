import type { Metadata } from "next";
import {
  DocumentFrame,
  GlyphList,
  GlyphRow,
  Mono,
  PageTitle,
  Prose,
  Section,
} from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "security — controls, and the limits we publish",
  description:
    "How digithings handles identity, audit and change: signed tokens and scoped keys, a request " +
    "id on every hop, secret scanning and dependency audits in CI, review before every production " +
    "release — plus the gaps we have not closed yet.",
};

// /security for a client, not a contributor: one or two sentences a row. The
// full record — threat model, STRIDE table, every residual risk — is the root
// SECURITY.md, linked from Disclosure. Every row is read out of the code, so
// two statements deliberately differ from SECURITY.md's prose: revocation is
// shipped but opt-in (a Redis jti blocklist), and audit redaction matches key
// names, not values. Limits is a selection, never presented as the full list.

const IDENTITY: { term: string; body: string }[] = [
  {
    term: "Signed tokens",
    body:
      "Access tokens are RS256 JWTs. Services verify them with a public key, so no service can " +
      "mint one.",
  },
  {
    term: "Scoped API keys",
    body:
      "Keys are hashed at rest and carry an explicit scope list, so a key can only do what it was " +
      "issued for.",
  },
  {
    term: "Fails closed",
    body:
      "Every protected route checks its scope. If auth is not configured, the route refuses " +
      "traffic instead of serving it.",
  },
  {
    term: "Revocation",
    body:
      "With Redis configured, a revoked key is blocked on its next request. Without it, issued " +
      "tokens stay valid until they expire.",
  },
];

const TRACEABILITY: { term: string; body: string }[] = [
  {
    term: "A request id on every hop",
    body: "Each request carries one id across every service call and into every log line.",
  },
  {
    term: "An audit trail on your host",
    body: "Workflow events go to a local log, with fields named like secrets redacted.",
  },
  {
    term: "No open doors",
    body:
      "Cross-origin access is an explicit allowlist, and every service call between modules has " +
      "a timeout.",
  },
];

const PIPELINE: { term: string; body: string }[] = [
  {
    term: "Secret scanning",
    body:
      "Every code pull request is scanned for leaked secrets, and the full history on every push " +
      "to the release branches. A finding fails the build.",
  },
  {
    term: "Dependency audits",
    body:
      "The Python services' locked dependencies are audited weekly and on every manifest change; " +
      "high and critical vulnerabilities block the merge. The JavaScript workspaces have a " +
      "matching lane.",
  },
  {
    term: "Private by default",
    body:
      "Every service binds to localhost, and debug endpoints stay off unless someone turns them on.",
  },
];

const SHIPPING: { term: string; body: string }[] = [
  {
    term: "Tested",
    body: "Each module's test suite runs on every pull request that touches it.",
  },
  {
    term: "Reviewed",
    body:
      "Every change that reaches production was reviewed at its own pull request, and a required " +
      "check refuses anything that was not.",
  },
  {
    term: "Built",
    body: "Code is linted, the shared libraries are type-checked, and every site builds in CI.",
  },
];

const LIMITS: { term: string; body: string }[] = [
  {
    term: "Private networks only",
    body:
      "The stack is designed for one host or a private network. Reach it over a VPN or a " +
      "hardened gateway, not a public port.",
  },
  {
    term: "Tenants are separated by key scope",
    body: "Storage-level isolation between tenants is not built yet.",
  },
  {
    term: "Retrieved content is not screened",
    body: "Documents pulled back by retrieval are not yet checked for prompt injection.",
  },
  {
    term: "The audit log is local and unsigned",
    body: "It records what happened, but cannot prove the record was never edited.",
  },
  {
    term: "Live trading is stubbed",
    body:
      "Broker adapters refuse to connect, and changes to live-trading code need a human " +
      "sign-off — a process gate, not a runtime interlock.",
  },
];

function Rows({ rows }: { rows: { term: string; body: string }[] }) {
  return (
    <GlyphList>
      {rows.map((r) => (
        <GlyphRow key={r.term} label={r.term}>
          {r.body}
        </GlyphRow>
      ))}
    </GlyphList>
  );
}

export default function SecurityPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle path="security" title="Controls, and their edges.">
              Every control here was checked against the code. The last section lists what is not
              covered yet.
            </PageTitle>
          </div>

          <Section id="identity" title="Identity" lede="digikey issues and verifies every credential.">
            <Rows rows={IDENTITY} />
          </Section>

          <Section
            id="traceability"
            title="Traceability"
            lede="On your own infrastructure, you can answer what happened."
          >
            <Rows rows={TRACEABILITY} />
          </Section>

          <Section id="pipeline" title="The pipeline" lede="Checks that fail the build, not file a note.">
            <Rows rows={PIPELINE} />
          </Section>

          <Section id="shipping" title="How change ships">
            <Rows rows={SHIPPING} />
            <Prose className="mt-[1.6rem]">
              <p>
                The tests, workflows and reviews are all in the{" "}
                <a
                  href="https://github.com/digithings-ai/digithings"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  public repository
                </a>
                .
              </p>
            </Prose>
          </Section>

          <Section id="limits" title="Limits" lede="The gaps worth weighing before you deploy.">
            <Rows rows={LIMITS} />
          </Section>

          <Section id="disclosure" title="Disclosure" lede="Please do not open a public issue.">
            <Prose>
              <p>
                Email the address in <Mono>SECURITY.md</Mono> with{" "}
                <Mono>[digithings Security]</Mono> in the subject. We acknowledge within 72 hours
                and agree a disclosure timeline within seven days.
              </p>
              <p>
                <a
                  href="https://github.com/digithings-ai/digithings/blob/main/SECURITY.md"
                  target="_blank"
                  rel="noopener noreferrer"
                >
                  SECURITY.md — full threat model and contact
                </a>
              </p>
            </Prose>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
    