import {
  Colophon,
  Footer,
  Marquee,
  NumberedStages,
  Reveal,
  StatCounter,
  WordReveal,
  type CounterStat,
  type MarqueeItem,
  type NumberedStage,
} from "@digithings/web";
import { DT_CONTACT_EMAIL, DT_FOOTER, DT_FOOTER_META } from "./_nav";
import { DtNav } from "@/components/DtNav";
import { HeroMesh } from "@/components/landing/HeroMesh";
import { ModuleManifest } from "@/components/landing/ModuleManifest";

// v8 landing for the DigiThings platform — 100% reference-sourced + expressive
// (#1450). A mouse-following mesh-gradient hero (HeroMesh + reveal-field
// HeroGraph) opens, then every visual block is a promoted @digithings/web
// primitive or token-backed utility: a drifting Marquee stack strip, a count-up
// StatCounter metrics band, the shared TerminalManifest, the NumberedStages
// principles spine, and the one big WordReveal pinned-blur claim. The mesh /
// graph / counters / reveal are client islands; the page stays a server
// component and exports statically. Every motion moment honors
// prefers-reduced-motion and reads with no JS (html.no-js fallbacks).

// The stack we build on — the core seven, drifting in the marquee right below
// the hero. Each carries its Simple Icons glyph where one exists
// (@digithings/web logos registry); NautilusTrader and LiteLLM have no mark
// and read text-only.
const STACK: MarqueeItem[] = [
  { name: "LangGraph", icon: "langgraph" },
  { name: "NautilusTrader" },
  { name: "Polars", icon: "polars" },
  { name: "Pydantic", icon: "pydantic" },
  { name: "LiteLLM" },
  { name: "MCP", icon: "modelcontextprotocol" },
  { name: "Docker", icon: "docker" },
];

// Real, honest facts — each count-up figure is a property of the stack, not a
// projection. "10 modules" matches the architecture head + the manifest total.
const METRICS: CounterStat[] = [
  { value: 10, label: "modules" },
  { value: 100, suffix: "%", label: "self-hosted" },
  { value: 0, label: "data retained" },
  { value: 1, label: "compose file" },
];

// The four properties of every module — verbatim from the prior principles grid,
// now a numbered spine.
const PRINCIPLES: NumberedStage[] = [
  {
    num: "01",
    title: "Self-hosted by default",
    mech: "One docker-compose file runs the whole stack on a laptop, a VM, or a cluster.",
  },
  {
    num: "02",
    title: "BYOK, every request",
    mech: "Anthropic, OpenAI, or any LiteLLM-compatible key — forwarded per-request, never stored.",
  },
  {
    num: "03",
    title: "Audit-on by default",
    mech: "Immutable JSONL audit, correlation IDs across every span, PII redacted before logs hit disk.",
  },
  {
    num: "04",
    title: "Backend-swappable",
    mech: "Swap vector DB or storage backend without touching business code.",
  },
];

export default function Home() {
  return (
    <>
      <DtNav />

      <main>
        <HeroMesh>
          <h1 className="dqhero-h1">
            <span className="ln">
              <span>Build agents on infrastructure</span>
            </span>
            <span className="ln">
              <span>
                <em>you own.</em>
              </span>
            </span>
          </h1>
          <p className="dqhero-lede">
            An open-core agentic stack — research, retrieval, and chat behind one supervisor.
            Self-hosted, BYOK, audit-on by default. No vendor lock-in, no opaque pipelines.
          </p>
          <div className="dqhero-cta">
            <p className="dqhero-scroll-label">Scroll to explore</p>
            <div className="dqhero-scroll" aria-hidden="true" />
          </div>
        </HeroMesh>

        <section className="border-y border-hair" aria-label="Built on">
          <Marquee
            items={STACK}
            tone="mute"
            speed={42}
            aria-label="Built on LangGraph, NautilusTrader, Polars, Pydantic, LiteLLM, MCP, and Docker"
            className="py-[0.95rem]"
          />
        </section>

        <section className="section" id="metrics">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// by the numbers"}</span>
              <h2>The platform, in four numbers.</h2>
              <p>
                No asterisks. Every figure is a real property of the stack — count them as you
                arrive.
              </p>
            </Reveal>
            <Reveal>
              <StatCounter stats={METRICS} className="mx-auto max-w-[880px]" />
            </Reveal>
          </div>
        </section>

        <section className="section section-architecture" id="architecture">
          <div className="wrap">
            <Reveal className="section-head center">
              <span className="kicker">{"// the architecture"}</span>
              <h2>Ten modules, wired into one.</h2>
              <p>
                A supervisor at the centre routes every request to the right module — chat, quant
                research, or retrieval. Each one self-hosted, audited, and swappable.
              </p>
            </Reveal>
            <ModuleManifest />
          </div>
        </section>

        <section className="section section-alt" id="principles">
          <div className="wrap">
            <Reveal className="section-head">
              <span className="kicker">{"// why digithings"}</span>
              <h2>Four properties of every module.</h2>
            </Reveal>
            <NumberedStages stages={PRINCIPLES} className="max-w-[760px]" />
          </div>
        </section>

        <section className="section" id="claim" aria-label="Own the whole stack">
          <div className="wrap">
            <WordReveal
              id="claim-reveal"
              text="Own the whole stack. No vendor lock-in. No opaque pipelines."
            />
          </div>
        </section>

        <section className="section text-center" id="contact">
          <Reveal className="wrap">
            <div className="font-mono text-[0.7rem] uppercase tracking-[0.16em] text-accent">
              Contact
            </div>
            <h2 className="mt-[0.6rem] font-display text-[clamp(1.6rem,3vw,2.4rem)] font-normal leading-[1.12] tracking-[-0.01em] text-ink">
              Questions, enterprise, or partnership.
            </h2>
            <p className="mx-auto mt-[0.8rem] max-w-[60ch] leading-[1.6] text-ink-soft">
              The stack is open core — reach out for managed deployments, on-prem setups, or
              anything else about the platform.
            </p>
            <div className="mt-[2rem] flex flex-wrap justify-center gap-[0.8rem]">
              <a
                className="btn btn-primary"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20inquiry`}
              >
                Email us <span aria-hidden="true">→</span>
              </a>
              <a
                className="btn btn-ghost"
                href={`mailto:${DT_CONTACT_EMAIL}?subject=DigiThings%20enterprise`}
              >
                Enterprise
              </a>
            </div>
            <p className="mt-[1.4rem] font-mono text-[0.88rem] text-ink-mute">
              <a
                className="text-accent [text-underline-offset:2px] hover:text-ink"
                href={`mailto:${DT_CONTACT_EMAIL}`}
              >
                {DT_CONTACT_EMAIL}
              </a>
            </p>
          </Reveal>
        </section>
      </main>

      <Colophon name="digi" suffix="things" />
      <Footer links={DT_FOOTER} meta={DT_FOOTER_META} />
    </>
  );
}
