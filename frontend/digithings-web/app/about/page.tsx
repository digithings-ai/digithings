import type { Metadata } from "next";
import Link from "next/link";
import { Reveal } from "@digithings/web";
import { DtFooter } from "@/components/DtFooter";
import { Mono, PageHead } from "../_company/prose";
import { DtNav } from "@/components/DtNav";

export const metadata: Metadata = {
  title: "about — open AI infrastructure you can host",
  description:
    "digithings is a modular, MIT-licensed AI infrastructure repository: self-hostable anywhere, " +
    "bring your own provider keys, every step traceable. Built to compose with the stack you " +
    "already run — not to replace it.",
};

// /about — the positioning page. Every claim here is a property of the repo that
// a reader can check: the licence (root LICENSE, MIT), the module count (the
// shared modules registry in @digithings/web — four core plus five support are
// shipping; digistore and digilink carry tier: "roadmap", so the lede says
// "nine shipping … plus two more marked roadmap" rather than the flat "eleven"
// the homepage uses. A page whose thesis is that every claim is checkable
// cannot fold two unbuilt modules into a headline count), the
// single compose file (root docker-compose.yml), provider credentials the stack
// does not persist, and the traceability surfaces (X-Request-ID middleware in
// digibase.http, the JSONL audit trail written by each service's audit_log() and
// redacted through digibase.audit, digismith spans). No adjectives standing in
// for evidence — where a boundary exists, /security states it.
//
// "Bring your own tokens" says the stack PERSISTS no provider credentials, and
// that they are "supplied per request or read from your own environment". It
// deliberately does NOT say every provider key you hand it is forwarded on the
// request, because that is not true today: digigraph/llm_auth.py's
// push_byok_header() wires X-BYOK-Key through to the client for provider
// "openai" and "openrouter" only. With provider "anthropic" the key is accepted,
// parked on a contextvar, and the call still runs on the env-configured
// credentials (llm_auth.py:92-96 — no set_byok branch). Fixing that path is
// tracked on its own branch; until it lands, this copy must not promise it.
// Page grammar is the site's own: .section / .wrap / .section-head / .kicker,
// DtNav + DtFooter, no new CSS families.

// The four properties of the repository as a whole. Each one is a fact with a
// filename behind it, named in the body copy so it stays checkable.
const POSITION: { title: string; body: string }[] = [
  {
    title: "MIT, and public",
    body:
      "The whole repository is MIT-licensed and readable without an account — the " +
      "orchestration graph, the quant engine wiring, the auth service, the tests, the CI. " +
      "No open-core teaser with the useful half held back.",
  },
  {
    title: "Self-hostable anywhere",
    body:
      "One docker-compose.yml runs the stack on a laptop, a VM, or a cluster. Every service " +
      "binds loopback by default, so nothing is on a public interface until you decide to put " +
      "it there.",
  },
  {
    title: "Bring your own tokens",
    body:
      "Anthropic, OpenAI, or anything LiteLLM speaks. The stack persists no provider credentials — " +
      "they are supplied per request or read from your own environment — so the model provider, the " +
      "budget, and the data boundary stay yours.",
  },
  {
    title: "A glass box, not a black box",
    body:
      "A correlation ID enters at the edge and rides every hop; workflow steps land in a local " +
      "JSONL audit trail — appended, never rewritten — and in digismith spans. You can read what " +
      "the system did, step by step, after the fact.",
  },
];

// What the stack composes with, rather than competes against. These are the
// dependencies the code actually imports — the same seven the homepage's
// #integrations section names, sourced from the root CLAUDE.md non-negotiables.
const COMPOSES_WITH: { name: string; role: string }[] = [
  { name: "LangGraph", role: "supervisor + sub-graph orchestration" },
  { name: "NautilusTrader", role: "every backtest and optimise path" },
  { name: "Polars", role: "dataframes by rule; pandas only at the Nautilus and yfinance edges" },
  { name: "Pydantic v2", role: "typed models at every boundary" },
  { name: "LiteLLM", role: "provider routing and response caching" },
  { name: "MCP", role: "every capability exposed as a discoverable tool" },
  { name: "Docker", role: "one compose file for the whole topology" },
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
          digithings is an open-source, modular AI infrastructure repository. Nine shipping modules
          — orchestration, quant research, retrieval, chat, auth, tracing, heartbeat and audit,
          a markdown vault, and the shared library the rest sit on — plus two more marked roadmap in the registry rather
          than quietly counted as built. You run them on your own
          hardware, against your own provider keys, with every step of every run readable
          afterwards. It is a set of parts you assemble, not a platform you move into.
        </PageHead>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// four properties"}</span>
              <h2>What that means, concretely.</h2>
              <p>
                Four claims, each one checkable against the repository rather than against a
                brochure.
              </p>
            </Reveal>
            <div className="grid gap-[1.1rem] sm:grid-cols-2">
              {POSITION.map((p) => (
                <Reveal key={p.title} className="mod-card">
                  <h3>{p.title}</h3>
                  <p className="text-[0.92rem] leading-[1.65] text-ink-soft">{p.body}</p>
                </Reveal>
              ))}
            </div>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// compatibility"}</span>
              <h2>It plugs into what you already run.</h2>
              <p>
                Compatibility is a design goal, not a migration story. digithings is not a
                replacement for your orchestration framework, your data stack, your model provider,
                or your execution venue — it is the wiring between them, and it uses the same tools
                you would have reached for.
              </p>
            </Reveal>
            <ul className="m-0 grid list-none gap-0 p-0">
              {COMPOSES_WITH.map((c) => (
                <li
                  key={c.name}
                  className="flex flex-wrap items-baseline gap-x-[1rem] gap-y-[0.2rem] border-t border-hair py-[0.85rem] last:border-b"
                >
                  <span className="font-mono text-[0.92rem] text-ink">{c.name}</span>
                  <span className="text-[0.88rem] text-ink-mute">{c.role}</span>
                </li>
              ))}
            </ul>
            <p className="mt-[1.6rem] max-w-[62ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              The corollary is that you can take a piece and leave the rest. The vector store and
              the LLM provider are both behind interfaces; swapping one is a configuration change,
              not a fork.
            </p>
          </div>
        </section>

        <section className="section">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// the glass box"}</span>
              <h2>Traceable by construction.</h2>
              <p>
                &ldquo;Explainable&rdquo; is a claim about a model. This is a claim about a system:
                the path a request took through it is recorded, and you own the recording.
              </p>
            </Reveal>
            <div className="grid gap-[1.1rem] md:grid-cols-3">
              <Reveal className="mod-card">
                <h3>One id, every hop</h3>
                <p className="text-[0.92rem] leading-[1.65] text-ink-soft">
                  All six FastAPI services install the shared <Mono>X-Request-ID</Mono> middleware
                  from <Mono>digibase.http</Mono>. The id is read from the request or generated,
                  attached to every log record, forwarded on outbound service-to-service calls, and
                  echoed on the response — so one identifier stitches a whole run together.
                </p>
              </Reveal>
              <Reveal className="mod-card">
                <h3>An audit trail on disk</h3>
                <p className="text-[0.92rem] leading-[1.65] text-ink-soft">
                  Workflow events are appended to a local JSONL audit log, redacted on the way in.
                  It is a file you own on a host you control — not a retention policy you agreed to.
                </p>
              </Reveal>
              <Reveal className="mod-card">
                <h3>Tools you can enumerate</h3>
                <p className="text-[0.92rem] leading-[1.65] text-ink-soft">
                  Capabilities are exposed as MCP tools with typed Pydantic schemas, so the set of
                  actions an agent can take is a list you can read — not an emergent property of a
                  prompt.
                </p>
              </Reveal>
            </div>
            <p className="mt-[1.8rem] max-w-[64ch] text-[0.95rem] leading-[1.7] text-ink-soft">
              Where that recording has gaps — and it does — they are written down. The audit log is
              per-host with no signed chain, redaction is name-based rather than content-based, and
              live-trading adapters are stubs behind a review gate rather than a runtime interlock.{" "}
              <Link className="text-accent [text-underline-offset:2px] hover:text-ink" href="/security">
                The security page states each limit
              </Link>
              .
            </p>
          </div>
        </section>

        <section className="section section-alt">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// read the source"}</span>
              <h2>Start where you like.</h2>
              <p>
                The API reference is written from the codebase and merged with the same module data
                this site is built on. The repository is the rest of the answer.
              </p>
            </Reveal>
            <div className="flex flex-wrap gap-[0.8rem]">
              <Link className="btn btn-primary" href="/docs">
                Read the docs <span aria-hidden="true">→</span>
              </Link>
              <a
                className="btn btn-ghost"
                href="https://github.com/digithings-ai/digithings"
                target="_blank"
                rel="noopener noreferrer"
              >
                Browse the repository
              </a>
              <Link className="btn btn-ghost" href="/quality">
                How it is tested
              </Link>
            </div>
          </div>
        </section>
      </main>

      <DtFooter />
    </>
  );
}
