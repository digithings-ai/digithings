import {
  CodeTabs,
  Colophon,
  ContactMailto,
  CtaLink,
  Figure,
  NumberedStages,
  OdometerStrip,
  RepoActivity,
  Reveal,
  SocialRow,
  StackRow,
  WordReveal,
  type CodeSample,
  type NumberedStage,
  type OdometerStat,
  type StackItem,
} from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ModuleManifest } from "@/components/landing/ModuleManifest";
import {
  CONTRIBUTING_URL,
  REPO_CLONE,
  REPO_LIVE,
  REPO_URL,
  repoActivity,
} from "@/lib/repoActivity";
import {
  BYOK_KEYS_STORED,
  COMPOSE_DEFAULT,
  COMPOSE_SERVICES,
  COUNTED_AT,
  ROADMAP_MODULES,
  SEARCH_BACKENDS,
  SHIPPING_MODULES,
} from "@/lib/siteCounts";

// v9 landing for the digithings platform — rebuilt on the opencode.ai language
// (D1, #4429). A small-type mono hero states the one-line claim, the install
// command is a segmented tab group with a copy affordance, and every visual
// block below is a promoted @digithings/ui primitive rendered inside a numbered
// `Fig N` figure: the ambient mesh/graph field (repurposed from the retired
// full-bleed hero), the OdometerStrip metrics band, the shared TerminalManifest,
// the NumberedStages principles spine, RepoActivity, and the one big WordReveal
// claim. The page stays a server component and exports statically; the mesh /
// graph / counters / reveal are client islands and honor prefers-reduced-motion
// and no-JS.
//
// Every count is single-sourced in lib/siteCounts.ts (D1): the module split is
// derived from the shared registry, the rest are dated repository snapshots —
// no page restates a number. Nothing here is a projection and nothing promises
// live trading.

// The install channels that actually exist in the repository README — there is
// no `curl | sh` installer, so no such tab is offered. Each tab is the complete
// path from clone to a running stack: Docker (`make up`), the no-Docker local
// stack (`make stack-local`), and the prebuilt GHCR images (`make up-ghcr`).
const INSTALL: CodeSample[] = [
  {
    label: "docker",
    code: `${REPO_CLONE}.git\ncd digithings\nmake up`,
  },
  {
    label: "local",
    code: `${REPO_CLONE}.git\ncd digithings\nmake stack-local`,
  },
  {
    label: "ghcr",
    code: `${REPO_CLONE}.git\ncd digithings\nmake pull-ghcr && make up-ghcr`,
  },
];

// Every figure is countable in the repo (#1846) and single-sourced above:
//   9  — non-roadmap modules in the shared registry (2 are roadmap: digistore,
//        digilink). The manifest below self-discloses the same split.
//   23 — services under `services:` in the single docker-compose.yml.
//   3  — live vector backends behind one client, fail-closed at startup:
//        Cloudflare Vectorize → Azure AI Search → Chroma.
//   0  — BYOK keys stored: the key arrives per-request in `x-byok-key` and is
//        forwarded upstream, never persisted or logged.
// Rendered by the OdometerStrip: each digit is a 0–9 reel that rolls to its
// value on arrival; reduced motion and no-JS ship the settled final figures.
const METRICS: OdometerStat[] = [
  { value: String(SHIPPING_MODULES), label: "modules shipping" },
  { value: String(COMPOSE_SERVICES), label: "compose services" },
  { value: String(SEARCH_BACKENDS), label: "vector backends" },
  { value: String(BYOK_KEYS_STORED), label: "keys stored" },
];

// The packages the stack is actually assembled from, named deliberately and in
// full (#1846) — compatibility is the differentiator, so the dependency list IS
// the pitch. Rendered by the shared StackRow/StackLogo primitives: a slug in the
// logos registry gets its real vendor mark, anything else degrades to a monogram
// chip. NautilusTrader, LiteLLM, Cheaper Inference, Chroma, Azure AI Search and
// Assistant UI publish no single-path monochrome SVG, so they read as monograms —
// expected, not a bug. Every slug below is verified against components/logos.ts.
const INTEGRATIONS: { label: string; items: StackItem[] }[] = [
  {
    label: "orchestration & models",
    items: [
      { name: "LangGraph", icon: "langgraph" },
      { name: "LiteLLM", icon: null, mono: "LL" },
      { name: "Cheaper Inference", icon: null, mono: "CI" },
      { name: "MCP", icon: "modelcontextprotocol" },
      { name: "OpenAI SDK", icon: "openai" },
      { name: "Pydantic", icon: "pydantic" },
      { name: "FastAPI", icon: "fastapi" },
    ],
  },
  {
    label: "quant, data & retrieval",
    items: [
      { name: "NautilusTrader", icon: null, mono: "NT" },
      { name: "Optuna", icon: "optuna" },
      { name: "Polars", icon: "polars" },
      { name: "Chroma", icon: null, mono: "Ch" },
      { name: "Azure AI Search", icon: null, mono: "AZ" },
      { name: "Supabase", icon: "supabase" },
      { name: "Postgres", icon: "postgresql" },
    ],
  },
  {
    label: "runtime, surface & observability",
    items: [
      { name: "Docker", icon: "docker" },
      { name: "OpenTelemetry", icon: "opentelemetry" },
      { name: "Prometheus", icon: "prometheus" },
      { name: "Redis", icon: "redis" },
      { name: "Next.js", icon: "nextdotjs" },
      { name: "React", icon: "react" },
      { name: "Assistant UI", icon: null, mono: "AU" },
    ],
  },
];

// The four properties of every module — a numbered spine. Counts are the
// single-sourced constants so the copy cannot drift from the figures above.
const PRINCIPLES: NumberedStage[] = [
  {
    num: "01",
    title: "Self-hosted by default",
    mech:
      `One docker-compose file, ${COMPOSE_SERVICES} services, on a laptop or any host you own — ` +
      `${COMPOSE_DEFAULT} up by default and the rest behind named profiles you turn on: digichat, ` +
      "digivault, the search MCP, the heartbeat, observability, and the LiteLLM cache.",
  },
  {
    num: "02",
    title: "BYOK, every request",
    mech: "Anthropic, OpenAI, or any LiteLLM-compatible key — forwarded per-request, never stored.",
  },
  {
    num: "03",
    title: "Audit-on by default",
    mech: "Append-only JSONL audit and a correlation ID on every service hop. Events record a prompt's length, never its text — tail events.jsonl and check.",
  },
  {
    num: "04",
    title: "Backend-swappable",
    mech:
      `${SEARCH_BACKENDS} live vector backends — Cloudflare Vectorize, Azure AI Search and Chroma — ` +
      "behind one client, swappable without touching business code.",
  },
];

export default function Home() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1}>
        {/* Small-type mono hero (opencode language): the one-line claim, the
            lede, and the install command as a segmented tab group. No mesh here
            any more — the art moved into the Fig 1 media block below. */}
        <section className="section pb-0" aria-labelledby="hero-claim">
          <div className="wrap">
            <span className="kicker">{"// digithings"}</span>
            <h1
              id="hero-claim"
              className="mt-[0.9rem] font-mono text-[22px] font-normal leading-[1.45] tracking-[-0.01em] text-ink"
            >
              AI infrastructure, in a glass box you own.
            </h1>
            <p className="mt-[1rem] max-w-[62ch] text-[1.02rem] leading-[1.7] text-ink-soft">
              Build and ship AI applications on infrastructure you own — your hosts, your keys, your
              choice of model.
            </p>
            <div className="mt-[1.6rem] max-w-[46rem]">
              <CodeTabs samples={INSTALL} />
            </div>
            <div className="mt-[1.4rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/chat">Ask digichat</CtaLink>
              <CtaLink href="#metrics" variant="ghost">
                See the numbers
              </CtaLink>
            </div>
          </div>
        </section>

        {/* Fig 1 — the ambient mesh/graph field, repurposed from the retired
            full-bleed hero into a bounded, looping media block. The canvas and
            graph are the same client art; the caption is honest about what it
            is (a live field, not a screencast). */}
        <section className="section pb-0" aria-label="Ambient field">
          <div className="wrap">
            <Figure
              n={1}
              caption="The ambient mesh and graph field, drawn live in the browser — no image, no video."
            >
              <div className="relative aspect-[16/9] w-full overflow-hidden border border-hair">
                <HeroMesh variant="media" />
              </div>
            </Figure>
          </div>
        </section>

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// by the numbers"}</span>
              <h2>The platform, in four numbers.</h2>
              <p>
                No asterisks — every figure is countable in the repo, and every one is single-sourced
                in this site&apos;s <code className="font-mono text-ink">lib/siteCounts.ts</code>. The
                manifest below names which modules ship and which are still roadmap.
              </p>
            </Reveal>
            <Reveal>
              <Figure
                n={2}
                caption={`Counted ${COUNTED_AT}; the module split is derived from the shared registry.`}
              >
                <OdometerStrip stats={METRICS} className="mx-auto max-w-[880px]" />
              </Figure>
            </Reveal>
          </div>
        </section>

        <section className="section section-architecture" id="architecture">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the architecture"}</span>
              {/* "9", not "11": the #metrics band one screen above renders the
                  same shipped-module count, so a scanning reader never meets two
                  different headline-level numbers for the same thing. The split
                  is derived from the registry. */}
              <h2 className="text-balance">{SHIPPING_MODULES} modules. One toolkit.</h2>
              <p>
                The {SHIPPING_MODULES} that ship run standalone or compose with the rest — retrieval,
                quant research and chat, plus the auth, tracing and audit any deployment needs.{" "}
                {ROADMAP_MODULES} more are on the roadmap; the manifest below marks which.
              </p>
            </Reveal>
            <ModuleManifest />
          </div>
        </section>

        {/* Integrations: the dependency list as the pitch. Uses the shared
            StackRow primitive — no app-local component, no new class family. */}
        <section className="section" id="integrations">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// integrations"}</span>
              <h2>Built on what you already run.</h2>
              <p>
                Every module is assembled from open-source libraries you can name, version, and
                swap — no forks, no reimplementations. That is why this drops into an existing
                deployment instead of asking you to replace one.
              </p>
            </Reveal>
            {INTEGRATIONS.map((group) => (
              <Reveal key={group.label} className="mx-auto mt-[1.7rem] max-w-[880px]">
                <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-mute">
                  {group.label}
                </div>
                <StackRow items={group.items} />
              </Reveal>
            ))}
          </div>
        </section>

        {/* "built on what you already run" (open dependencies) → "maintained in
            the open" (the repo itself). Placed here rather than under the hero so
            its figures never sit adjacent to the #metrics odometer, where two
            number-bearing blocks would read as one restated twice. Plain
            .section: section-alt stays the single accent before the claim. */}
        <section className="section" id="repository">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the repository"}</span>
              <h2>Maintained in the open.</h2>
              <p>
                One MIT-licensed monorepo, public and moving. Below are the most recent pull
                requests to land on{" "}
                <code className="font-mono text-ink">{repoActivity.branch}</code> — each one you
                can open and read, not a changelog entry we wrote about ourselves.
              </p>
            </Reveal>
            <Reveal>
              <RepoActivity
                variant="detailed"
                snapshot={repoActivity}
                repoUrl={REPO_URL}
                live={REPO_LIVE}
                cloneCommand={REPO_CLONE}
                contributingUrl={CONTRIBUTING_URL}
                className="mx-auto mt-[2rem] max-w-[980px]"
              />
            </Reveal>
          </div>
        </section>

        <section className="section section-alt" id="principles">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// why digithings"}</span>
              <h2>Nobody knows which vendor wins.</h2>
              <p>
                The field moves faster than any bet you could place on it, so this architecture
                declines to place one. Nothing here is married to a provider: the stack is
                self-hosted, keys arrive per request, and models and vector backends are
                configuration rather than code. When the leader changes, you change one setting —
                not the application on top.
              </p>
            </Reveal>
            <NumberedStages stages={PRINCIPLES} className="max-w-[760px]" />
          </div>
        </section>

        {/* No .section padding here: the WordReveal track is its own breathing
            room (the line rides in, pins at mid-viewport for a beat, and the
            page flows on) — section padding on top of it read as a dead gap. */}
        <section id="claim" aria-label="You own the stack, the keys, and the infrastructure">
          <div className="wrap">
            {/* The owner's own line, and the one claim the whole page exists to
                support. Three sentences on purpose: WordReveal fills word by
                word, so the repetition lands as three separate beats rather
                than one clause. */}
            <WordReveal
              id="claim-reveal"
              text="You own the stack. You own the keys. You own the infra."
            />
          </div>
        </section>

        <section className="section text-center" id="contact">
          <Reveal className="wrap">
            <div className="section-head center">
              <div className="kicker">Contact</div>
              <h2>Questions, enterprise, or partnership.</h2>
              <p>
                The whole monorepo is MIT-licensed and public — take it and run it yourself. What
                we sell is the integration work: fitting these modules to the stack you already
                have, on your own infrastructure.
              </p>
            </div>
            <div className="mt-[2rem] flex flex-wrap justify-center gap-[0.8rem]">
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className={buttonVariants({ variant: "default" })}
                subject="digithings%20inquiry"
              >
                Email us <span aria-hidden="true">→</span>
              </ContactMailto>
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className={buttonVariants({ variant: "ghost" })}
                subject="digithings%20enterprise"
              >
                Enterprise
              </ContactMailto>
            </div>
            <p className="mt-[1.4rem] font-mono text-[0.88rem] text-ink-mute">
              <ContactMailto email={DT_CONTACT_EMAIL}
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                showAddress
              >
                Or email us directly
              </ContactMailto>
            </p>
            <div className="mt-[1.6rem] flex justify-center">
              <SocialRow />
            </div>
          </Reveal>
        </section>
      </main>

      {/* sweep: the flagship page opts into the reference footer's glow
          sweep — every other consumer keeps the outline-only default. */}
      <Colophon name="digi" suffix="things" sweep />
      <DtFooter />
    </>
  );
}
