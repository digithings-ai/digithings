import {
  Colophon,
  NumberedStages,
  OdometerStrip,
  RepoActivity,
  Reveal,
  SocialRow,
  StackRow,
  WordReveal,
  type NumberedStage,
  type OdometerStat,
  type StackItem,
} from "@digithings/web";
import { ContactMailto } from "@digithings/web";
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

// v8 landing for the digithings platform — 100% reference-sourced + expressive
// (#1450). A mouse-following mesh-gradient hero (HeroMesh + reveal-field
// HeroGraph) opens, then every visual block is a promoted @digithings/web
// primitive or token-backed utility: a digit-roll OdometerStrip metrics band,
// the shared TerminalManifest, the NumberedStages principles spine, the
// RepoActivity section, and the one big WordReveal claim. The mesh / graph /
// counters / reveal are client islands; the page stays a server component and
// exports statically. Every motion moment honors prefers-reduced-motion and
// reads with no JS (html.no-js fallbacks).
//
// The slot under the hero used to hold a drifting <Marquee> of the seven core
// dependencies, then a RepoStrip of snapshot figures. Both are gone: the
// marquee named libraries the #integrations section already names, and the
// strip restated counts that now live once in <RepoActivity> further down.

// Every figure here is countable in the repo — no projections, no asterisks
// (#1846). Each one is checked against the code, and the band must not
// contradict the manifest right below it, which self-discloses "9 online · 2 on
// the roadmap" (computed from the registry, so it tracks automatically):
//   9  — non-roadmap modules in the shared `modules` registry (2 are roadmap:
//        digistore, digilink). digivault was missing from the registry until it was
//        added here — it ships
//        a FastAPI service on 8004 behind its own compose profile and had been
//        missing. This deliberately does NOT say "11", which is what used to sit
//        14 lines under "no asterisks".
//   16 — services under `services:` in the single 460-line docker-compose.yml.
//   2  — live vector backends behind one client: Chroma and Azure AI Search
//        (digisearch/src/digisearch/server.py fails startup unless one is
//        configured).
//   0  — BYOK keys stored: the key arrives per-request in `x-byok-key` and is
//        forwarded upstream, never persisted or logged
//        (frontend/digichat/src/app/api/chat/route.ts).
// Rendered by the OdometerStrip (#1452 promotion): each digit is a 0–9 reel
// that rolls to its value on arrival; reduced motion and no-JS ship the
// settled final figures.
const METRICS: OdometerStat[] = [
  { value: "9", label: "modules shipping" },
  { value: "16", label: "compose services" },
  { value: "2", label: "vector backends" },
  { value: "0", label: "keys stored" },
];

// The packages the stack is actually assembled from, named deliberately and in
// full (#1846) — compatibility is the differentiator, so the dependency list IS
// the pitch. This section is also why the marquee above it was removable: it named
// a subset of these on a loop and added nothing. Rendered by the shared
// StackRow/StackLogo primitives (@digithings/web): a slug present in the logos
// registry gets its real vendor mark, anything else degrades to a monogram
// chip. NautilusTrader, LiteLLM, Chroma and Azure AI Search publish no
// single-path monochrome SVG, so they read as monograms — expected, not a bug.
// Every slug below is verified against components/logos.ts.
const INTEGRATIONS: { label: string; items: StackItem[] }[] = [
  {
    label: "orchestration & models",
    items: [
      { name: "LangGraph", icon: "langgraph" },
      { name: "LiteLLM", icon: null, mono: "LL" },
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
    ],
  },
];

// The four properties of every module — verbatim from the prior principles grid,
// now a numbered spine.
const PRINCIPLES: NumberedStage[] = [
  {
    num: "01",
    title: "Self-hosted by default",
    mech:
      "One docker-compose file, sixteen services, on a laptop or any host you own — eight up by " +
      "default and the rest behind named profiles you turn on: digichat, digivault, the search MCP, " +
      "the heartbeat, observability, and the LiteLLM cache.",
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
    mech: "Two live vector backends — Chroma and Azure AI Search — behind one client, swappable without touching business code.",
  },
];

export default function Home() {
  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1}>
        <HeroMesh>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>AI infrastructure</span>
            </span>
            <span className="ln">
              <span>in a glass box</span>
            </span>
            <span className="ln">
              <span>
                <em>you own</em>
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            Build and ship AI applications on infrastructure you own — your hosts, your keys, your
            choice of model.
          </p>
          <div className="dqhero-cta">
            {/* Claim + install: shared .cmdline (site.css) is the diegetic
                proof; the loud control is ink/paper, never an accent pill. */}
            <p className="cmdline">
              <span className="prompt">$</span>
              git clone https://github.com/digithings-ai/digithings.git
            </p>
            <a className="btn btn-primary" href="/chat">
              Ask digichat
            </a>
            <a className="dqhero-scroll-label" href="#metrics">
              Scroll to explore
            </a>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// by the numbers"}</span>
              <h2>The platform, in four numbers.</h2>
              <p>
                No asterisks — every figure is countable in the repo. Nine modules ship today and
                two are still on the roadmap; the manifest below names which.
              </p>
            </Reveal>
            <Reveal>
              <OdometerStrip stats={METRICS} className="mx-auto max-w-[880px]" />
            </Reveal>
          </div>
        </section>

        <section className="section section-architecture" id="architecture">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the architecture"}</span>
              {/* nowrap from md up so the claim holds one line; it still wraps on
                  phones, where forcing one line would shrink it to nothing.
                  "Nine", not "Eleven" (full-UI-suite critique, P2): the
                  #metrics section one screen above states, and the odometer
                  literally renders, "9" shipped modules — a scanning reader
                  hitting two different headline-level numbers back to back
                  reads as a contradiction, even though both are correct under
                  their own count (nine shipped vs. eleven total registered).
                  The 9-shipped/2-roadmap split already lives in the body copy
                  below; the headline now matches the number it is standing
                  next to. */}
              <h2 className="md:whitespace-nowrap">Nine modules. One toolkit.</h2>
              <p>
                The nine that ship run standalone or compose with the rest — retrieval, quant
                research and chat, plus the auth, tracing and audit any deployment needs. Two more
                are on the roadmap; the manifest below marks which.
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
              <ContactMailto email={DT_CONTACT_EMAIL} className="btn btn-primary" subject="digithings%20inquiry">
                Email us <span aria-hidden="true">→</span>
              </ContactMailto>
              <ContactMailto email={DT_CONTACT_EMAIL} className="btn btn-ghost" subject="digithings%20enterprise">
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
