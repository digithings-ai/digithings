import {
  CodeTabs,
  Colophon,
  ContactMailto,
  CtaLink,
  Figure,
  NumberedStages,
  OdometerStrip,
  RepoActivity,
  SocialRow,
  StackRow,
  TerminalManifest,
  WordReveal,
  modules,
  type CodeSample,
  type NumberedStage,
  type OdometerStat,
  type StackItem,
  type TerminalManifestRow,
} from "@digithings/ui";
import { buttonVariants } from "@digithings/ui/ui";
import { DT_CONTACT_EMAIL } from "@/app/_nav";
import { DtFooter } from "@/components/DtFooter";
import { DtNav } from "@/components/DtNav";
import { moduleActivity, CONTRIBUTING_URL, REPO_CLONE, REPO_LIVE, REPO_URL, repoActivity } from "@/lib/repoActivity";
import {
  BYOK_KEYS_STORED,
  COMPOSE_DEFAULT,
  COMPOSE_SERVICES,
  COUNTED_AT,
  ROADMAP_MODULES,
  SEARCH_BACKENDS,
  SHIPPING_MODULES,
} from "@/lib/siteCounts";

// v9 landing — a fresh composition on the opencode.ai language (D1, #4429):
// monospace-first, deliberately small type, flat surfaces, no decoration and no
// reused legacy art. The whole page is canonical kit parts + the shared prose
// grammar; the module manifest, metrics, dependency list, repo activity and
// principles are the same facts the old page carried, re-presented simply.
//
// Every count is single-sourced in lib/siteCounts.ts. Nothing here is a
// projection and nothing promises live trading.

// The install channels that exist in the repository README — there is no
// `curl | sh` installer, so no tab invents one. Each is the complete path from
// clone to a running stack.
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

const METRICS: OdometerStat[] = [
  { value: String(SHIPPING_MODULES), label: "modules shipping" },
  { value: String(COMPOSE_SERVICES), label: "compose services" },
  { value: String(SEARCH_BACKENDS), label: "vector backends" },
  { value: String(BYOK_KEYS_STORED), label: "keys stored" },
];

// The packages the stack is assembled from — compatibility is the differentiator,
// so the dependency list is the pitch. Rendered by StackRow/StackLogo: a slug in
// the logos registry gets its real vendor mark, anything else a monogram chip.
// Slugs verified against components/logos.ts.
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

const PRINCIPLES: NumberedStage[] = [
  {
    num: "01",
    title: "Self-hosted by default",
    mech:
      `One docker-compose file, ${COMPOSE_SERVICES} services, on a laptop or any host you own — ` +
      `${COMPOSE_DEFAULT} up by default and the rest behind named profiles you turn on.`,
  },
  {
    num: "02",
    title: "BYOK, every request",
    mech: "Anthropic, OpenAI, or any LiteLLM-compatible key — forwarded per-request, never stored.",
  },
  {
    num: "03",
    title: "Audit-on by default",
    mech:
      "Append-only JSONL audit and a correlation ID on every service hop. Events record a " +
      "prompt's length, never its text — tail events.jsonl and check.",
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
  // Module manifest rows straight from the shared registry — the manifest names
  // which modules ship and which are roadmap, so no page needs a second list.
  const manifestRows: TerminalManifestRow[] = [...modules]
    .sort((a, b) => a.graphOrder - b.graphOrder)
    .map((m) => {
      const activity = moduleActivity(m.id);
      return {
        id: m.id,
        name: m.id,
        status: m.tier === "roadmap" ? "roadmap" : "online",
        blurb: m.role,
        detail: [m.tagline, "", ...m.summary, "", "stack   " + m.stack.map((s) => s.name).join("  ·  "), ...(activity ? ["repo    " + activity] : [])].join("\n"),
      };
    });

  return (
    <>
      <DtNav />

      <main id="main" tabIndex={-1}>
        {/* Hero: the one-line claim at 22px mono, the lede, and the install
            command as a segmented tab group with a copy affordance. No mesh, no
            animation — the opencode.ai language. */}
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
              choice of model. Self-hosted, MIT-licensed, every step traceable.
            </p>
            <div className="mt-[1.6rem] max-w-[46rem]">
              <CodeTabs samples={INSTALL} />
            </div>
            <div className="mt-[1.4rem] flex flex-wrap items-center gap-[0.8rem]">
              <CtaLink href="/chat">Ask digichat</CtaLink>
              <CtaLink href="/docs" variant="ghost">
                Read the docs
              </CtaLink>
            </div>
          </div>
        </section>

        {/* Fig 1 — the numbers, counted. No prose restates them. */}
        <section className="section" id="metrics">
          <div className="wrap">
            <span className="kicker">{"// by the numbers"}</span>
            <Figure
              n={1}
              caption={`Counted ${COUNTED_AT}; the module split is derived from the shared registry.`}
              className="mt-[1.2rem]"
            >
              <OdometerStrip stats={METRICS} />
            </Figure>
          </div>
        </section>

        {/* Fig 2 — the module manifest. Dense mono checklist; selecting a row
            types its detail at the cursor (primitive behaviour). */}
        <section className="section section-alt" id="architecture">
          <div className="wrap">
            <span className="kicker">{"// the modules"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              {SHIPPING_MODULES} ship today and run standalone or compose with the rest.{" "}
              {ROADMAP_MODULES} more are on the roadmap; the manifest marks which.
            </p>
            <Figure n={2} caption="The shared module registry, rendered as a terminal manifest." className="mt-[1.6rem]">
              <TerminalManifest
                className="mx-auto max-w-[980px]"
                prompt="//"
                command="modules"
                meta={`· ${SHIPPING_MODULES} online · ${ROADMAP_MODULES} on the roadmap`}
                rows={manifestRows}
                namePrefix="digi"
                aria-label="digithings module manifest"
              />
            </Figure>
          </div>
        </section>

        {/* Integrations — the dependency list as the pitch. */}
        <section className="section" id="integrations">
          <div className="wrap">
            <span className="kicker">{"// integrations"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              Every module is assembled from open-source libraries you can name, version, and swap —
              no forks, no reimplementations.
            </p>
            <div className="mt-[1.8rem] grid gap-[1.6rem]">
              {INTEGRATIONS.map((group) => (
                <div key={group.label}>
                  <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-ink-mute">
                    {group.label}
                  </div>
                  <StackRow items={group.items} />
                </div>
              ))}
            </div>
          </div>
        </section>

        {/* Why — the four properties as a numbered spine. */}
        <section className="section section-alt" id="principles">
          <div className="wrap">
            <span className="kicker">{"// why digithings"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              The field moves faster than any bet you could place on it, so this architecture
              declines to place one. Providers and backends are configuration, not code.
            </p>
            <NumberedStages stages={PRINCIPLES} className="mt-[2rem] max-w-[760px]" />
          </div>
        </section>

        {/* The repository — velocity, read from the snapshot. */}
        <section className="section" id="repository">
          <div className="wrap">
            <span className="kicker">{"// the repository"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              One MIT-licensed monorepo, public and moving. Recent pull requests to land on{" "}
              <code className="font-mono text-ink">{repoActivity.branch}</code> — each one you can
              open and read.
            </p>
            <RepoActivity
              variant="detailed"
              snapshot={repoActivity}
              repoUrl={REPO_URL}
              live={REPO_LIVE}
              cloneCommand={REPO_CLONE}
              contributingUrl={CONTRIBUTING_URL}
              className="mt-[1.8rem] max-w-[980px]"
            />
          </div>
        </section>

        {/* The claim. No arrows, no decoration — the line carries itself. */}
        <section id="claim" aria-label="You own the stack, the keys, and the infrastructure">
          <div className="wrap">
            <WordReveal
              id="claim-reveal"
              text="You own the stack. You own the keys. You own the infra."
            />
          </div>
        </section>

        <section className="section" id="contact">
          <div className="wrap">
            <span className="kicker">{"// contact"}</span>
            <p className="mt-[0.7rem] max-w-[64ch] text-[1rem] leading-[1.7] text-ink-soft">
              The whole monorepo is MIT-licensed and public — take it and run it yourself. What we
              sell is the integration work: fitting these modules to the stack you already have.
            </p>
            <div className="mt-[1.6rem] flex flex-wrap items-center gap-[0.8rem]">
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className={buttonVariants({ variant: "default" })}
                subject="digithings%20inquiry"
              >
                Email us
              </ContactMailto>
              <ContactMailto
                email={DT_CONTACT_EMAIL}
                className={buttonVariants({ variant: "ghost" })}
                subject="digithings%20enterprise"
              >
                Enterprise
              </ContactMailto>
              <span className="font-mono text-[0.82rem] text-ink-mute">
                <ContactMailto email={DT_CONTACT_EMAIL} showAddress>
                  {DT_CONTACT_EMAIL}
                </ContactMailto>
              </span>
            </div>
            <div className="mt-[1.6rem]">
              <SocialRow />
            </div>
          </div>
        </section>
      </main>

      {/* sweep: the flagship page opts into the reference footer's glow
          sweep — every other consumer keeps the outline-only default. */}
      <Colophon name="digi" suffix="things" sweep />
      <DtFooter />
    </>
  );
}
