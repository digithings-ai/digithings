import type { Metadata } from "next";
import { Mono, PageHead, RuledList, RuledRow } from "@digithings/ui";
import { CtaLink } from "@digithings/ui";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { ROADMAP_MODULES, SHIPPING_MODULES } from "@/lib/siteCounts";

export const metadata: Metadata = {
  title: "about — open AI infrastructure you can host",
  description:
    "digithings is a modular, MIT-licensed AI infrastructure repository: self-hostable anywhere, " +
    "bring your own provider keys, every step traceable. Built to compose with the stack you " +
    "already run — not to replace it.",
};

// /about — the positioning page, re-composed flat (D1, #4429): the opencode.ai
// language, not the old card grid. Every claim is a property of the repo a
// reader can check (root LICENSE MIT; the module count derived from the shared
// registry; the single compose file; provider credentials never persisted; the
// traceability surfaces). RuledList carries the definition rows — the plan's
// named grammar for this page — and nothing is stated here that /security does
// not state more precisely.

// The four properties of the repository as a whole, as ruled rows. Each is a
// fact with a filename behind it.
const POSITION: { term: string; body: string }[] = [
  {
    term: "MIT, and public",
    body:
      "The whole repository is MIT-licensed and readable without an account — the orchestration " +
      "graph, the quant engine wiring, the auth service, the tests, the CI. No open-core teaser " +
      "with the useful half held back.",
  },
  {
    term: "Self-hostable anywhere",
    body:
      "One docker-compose.yml runs the stack on a laptop, a VM, or a cluster. Every service binds " +
      "loopback by default, so nothing is on a public interface until you decide to put it there.",
  },
  {
    term: "Bring your own tokens",
    body:
      "Anthropic, OpenAI, or anything LiteLLM speaks. The stack persists no provider " +
      "credentials — they are supplied per request or read from your own environment — so the " +
      "model provider, the budget, and the data boundary stay yours.",
  },
  {
    term: "A glass box, not a black box",
    body:
      "A correlation ID enters at the edge and rides every hop; workflow steps land in a local " +
      "JSONL audit trail — appended, never rewritten — and in digismith spans. You can read what " +
      "the system did, step by step, after the fact.",
  },
];

// What the stack composes with rather than competes against — the dependencies
// the code actually imports.
const COMPOSES_WITH: { term: string; body: string }[] = [
  { term: "LangGraph", body: "Supervisor + sub-graph orchestration." },
  { term: "NautilusTrader", body: "Every backtest and optimise path." },
  { term: "Polars", body: "Dataframes by rule; pandas only at the Nautilus and yfinance edges." },
  { term: "Pydantic v2", body: "Typed models at every boundary." },
  { term: "LiteLLM", body: "Provider routing and response caching." },
  { term: "MCP", body: "Every capability exposed as a discoverable tool." },
  { term: "Docker", body: "One compose file for the whole topology." },
];

export default function AboutPage() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1} className="pt-[var(--dq-nav-h)]">
        <PageHead
          kicker={"// about"}
          title={
            <>
              Infrastructure, <em>not a product.</em>
            </>
          }
        >
          digithings is an open-source, modular AI infrastructure repository. {SHIPPING_MODULES}{" "}
          shipping modules — orchestration, quant research, retrieval, chat, auth, tracing,
          heartbeat and audit, a markdown vault, and the shared library the rest sit on — plus{" "}
          {ROADMAP_MODULES} more marked roadmap in the registry rather than quietly counted as
          built. You run them on your own hardware, against your own provider keys, with every step
          of every run readable afterwards. It is a set of parts you assemble, not a platform you
          move into.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// four properties"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Four claims, each one checkable against the repository rather than a brochure.
            </p>
            <RuledList>
              {POSITION.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// compatibility"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Compatibility is a design goal, not a migration story. digithings is not a replacement
              for your orchestration framework, your data stack, your model provider, or your
              execution venue — it is the wiring between them.
            </p>
            <RuledList>
              {COMPOSES_WITH.map((r) => (
                <RuledRow key={r.term} term={r.term}>
                  {r.body}
                </RuledRow>
              ))}
            </RuledList>
            <p className="mt-[1.4rem] max-w-[62ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              The corollary is that you can take a piece and leave the rest. The vector store and
              the LLM provider are both behind interfaces; swapping one is a configuration change,
              not a fork.
            </p>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <span className="kicker">{"// the glass box"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              &ldquo;Explainable&rdquo; is a claim about a model. This is a claim about a system:
              the path a request took through it is recorded, and you own the recording.
            </p>
            <RuledList>
              <RuledRow term="One id, every hop">
                All six FastAPI services install the shared <Mono>X-Request-ID</Mono> middleware
                from <Mono>digibase.http</Mono>. The id is read or generated, attached to every log
                record, forwarded on outbound calls, and echoed on the response.
              </RuledRow>
              <RuledRow term="An audit trail on disk">
                Workflow events are appended to a local JSONL audit log, redacted on the way in. It
                is a file you own on a host you control — not a retention policy you agreed to.
              </RuledRow>
              <RuledRow term="Tools you can enumerate">
                Capabilities are exposed as MCP tools with typed Pydantic schemas, so the set of
                actions an agent can take is a list you can read — not an emergent property of a
                prompt.
              </RuledRow>
            </RuledList>
            <p className="mt-[1.4rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              Where that recording has gaps — and it does — they are written down: the audit log is
              per-host with no signed chain, redaction is name-based, and live-trading adapters are
              stubs behind a review gate rather than a runtime interlock.{" "}
              <a className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                The security page states each limit
              </a>
              .
            </p>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <span className="kicker">{"// read the source"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              The API reference is written from the codebase and merged with the same module data
              this site is built on. The repository is the rest of the answer.
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/docs">Read the docs</CtaLink>
              <CtaLink href="https://github.com/digithings-ai/digithings" external variant="ghost">
                Browse the repository
              </CtaLink>
              <CtaLink href="/quality" variant="ghost">
                How it is tested
              </CtaLink>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
