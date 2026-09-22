import type { Metadata } from "next";
import type { ReactNode } from "react";
import {
  CtaLink,
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
  title: "about — open AI infrastructure you can host",
  description:
    "digithings is a modular, MIT-licensed AI infrastructure repository: self-hostable anywhere, " +
    "bring your own provider keys, every step traceable. Built to compose with the stack you " +
    "already run — not to replace it.",
};

// /about — the positioning page, rebuilt on the document grammar (D1, #4429):
// one framed column, hairline-separated sections, the `[*]` row grammar. The
// content is four checkable properties of the repository, the dependencies the
// code actually imports, and the glass box with its honest gaps. Nothing here
// is stated more precisely on /security, which the gaps line links to; the
// module counts the old hero carried now live only on the landing page.

const PROPERTIES: { label: string; body: string }[] = [
  {
    label: "MIT, and public",
    body:
      "The whole repository is MIT-licensed and readable without an account — the orchestration " +
      "graph, the quant engine wiring, the auth service, the tests and the CI, with no open-core " +
      "half held back",
  },
  {
    label: "Self-hostable anywhere",
    body:
      "One docker-compose.yml runs the stack on a laptop, a VM or a cluster, every service bound " +
      "to loopback until you decide to put it on a public interface",
  },
  {
    label: "Bring your own tokens",
    body:
      "Anthropic, OpenAI or anything LiteLLM speaks — supplied per request or read from your own " +
      "environment, with no provider credential persisted by the stack",
  },
  {
    label: "A glass box, not a black box",
    body:
      "A correlation ID enters at the edge and rides every hop, workflow steps land in a local " +
      "JSONL audit trail, and the path a request took stays readable after the fact",
  },
];

const COMPOSES_WITH: { label: string; body: string }[] = [
  { label: "LangGraph", body: "supervisor and sub-graph orchestration" },
  { label: "NautilusTrader", body: "every backtest and optimise path" },
  { label: "Polars", body: "dataframes by rule, with pandas only at the Nautilus and yfinance edges" },
  { label: "Pydantic v2", body: "typed models at every boundary" },
  { label: "LiteLLM", body: "provider routing and response caching" },
  { label: "MCP", body: "every capability exposed as a discoverable tool" },
  { label: "Docker", body: "one compose file for the whole topology" },
];

const GLASS_BOX: { label: string; body: ReactNode }[] = [
  {
    label: "One id, every hop",
    body: (
      <>
        All the FastAPI services install the shared <Mono>X-Request-ID</Mono> middleware from{" "}
        <Mono>digibase.http</Mono>, which reads or generates the id, attaches it to every log
        record, forwards it on outbound calls and echoes it on the response
      </>
    ),
  },
  {
    label: "An audit trail on disk",
    body:
      "Workflow events are appended to a local JSONL audit log, redacted on the way in — a file " +
      "you own on a host you control, not a retention policy you agreed to",
  },
  {
    label: "Tools you can enumerate",
    body:
      "Capabilities are MCP tools with typed Pydantic schemas, so the actions an agent can take " +
      "are a list you can read rather than an emergent property of a prompt",
  },
];

export default function AboutPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <DocumentFrame>
          <div className="px-[var(--page-pad)] py-[var(--page-step)]">
            <PageTitle title="Infrastructure, not a product.">
              digithings is an open-source, modular AI infrastructure repository — parts you
              assemble and run on your own hardware, against your own provider keys, rather than a
              platform you move into.
            </PageTitle>
          </div>

          <Section
            id="properties"
            title="Four properties"
            lede="Four claims, each one checkable against the repository rather than a brochure."
          >
            <GlyphList>
              {PROPERTIES.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
          </Section>

          <Section
            id="compatibility"
            title="Built to compose"
            lede="Compatibility is a design goal, not a migration story — these are the dependencies the code actually imports."
          >
            <GlyphList>
              {COMPOSES_WITH.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
            <div className="mt-[1.6rem]">
              <Prose>
                <p>
                  The corollary is that you can take a piece and leave the rest. The vector store
                  and the LLM provider both sit behind interfaces, so swapping one is a
                  configuration change, not a fork.
                </p>
              </Prose>
            </div>
          </Section>

          <Section
            id="glass-box"
            title="The glass box"
            lede="“Explainable” is a claim about a model; this is a claim about a system — the path a request took through it is recorded, and you own the recording."
          >
            <GlyphList>
              {GLASS_BOX.map((r) => (
                <GlyphRow key={r.label} label={r.label}>
                  {r.body}
                </GlyphRow>
              ))}
            </GlyphList>
            <div className="mt-[1.6rem]">
              <Prose>
                <p>
                  Where that recording has gaps — and it does — they are written down: the audit log
                  is per-host with no signed chain, redaction matches key names rather than values,
                  and live-trading adapters are stubs behind a review gate rather than a runtime
                  interlock. <a href="/security">The security page states each limit</a>.
                </p>
              </Prose>
            </div>
          </Section>

          <Section
            id="source"
            title="Read the source"
            lede="The API reference is written from the codebase and merged with the same module data this site is built on. The repository is the rest of the answer."
          >
            <div className="flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="https://github.com/digithings-ai/digithings" external variant="ghost">
                Browse the repository
              </CtaLink>
              <CtaLink href="/quality" variant="ghost">
                How it is tested
              </CtaLink>
            </div>
          </Section>
        </DocumentFrame>
      </main>

      <DtFooter />
    </>
  );
}
