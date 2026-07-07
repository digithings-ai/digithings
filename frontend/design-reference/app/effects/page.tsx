import "./effects.css";
import { ScrollyGraph, Terminal, type TermLine } from "@digithings/web";
import { AmbientMesh } from "@/components/effects/ambient-mesh";
import { ClipReveal } from "@/components/effects/clip-reveal";
import { CrossfadeSections } from "@/components/effects/crossfade-sections";
import { HeroGraphReference } from "@/components/hero-graph-reference";
import { ResearchPipeline } from "@/components/effects/research-pipeline";
import { RotatingPrompts } from "@/components/effects/rotating-prompts";
import { SectionMorph } from "@/components/effects/section-morph";
import { StackingPanels } from "@/components/effects/stacking-panels";

// The digithings.ai hero boot script (pre-v7 landing, frontend/digithings-web
// app/page.tsx history) — the signature content the Terminal component plays.
const BOOT: TermLine[] = [
  { kind: "cmd", text: "digithings --about" },
  { kind: "out", text: "open-core agentic stack · self-hosted" },
  { kind: "gap" },
  { kind: "cmd", text: "docker compose up -d" },
  { kind: "ok", name: "digigraph", text: "orchestration   :8000" },
  { kind: "ok", name: "digiquant", text: "quant engine    :8001" },
  { kind: "ok", name: "digisearch", text: "retrieval       :8002" },
  { kind: "ok", name: "digichat", text: "chat surface    :3005" },
  { kind: "arrow", text: "→ stack online · audit on · byok" },
];

/** Plain-text rendering of a TermLine for the no-JS <noscript> transcript —
 *  kept in lockstep with BOOT so the static fallback never drifts. */
function plainLine(l: TermLine): string {
  switch (l.kind) {
    case "gap":
      return "";
    case "cmd":
      return `$ ${l.text}`;
    case "ok":
      return `✓ ${l.name.padEnd(12)}${l.text}`;
    case "mod":
      return `${l.name.padEnd(13)}${l.text}  →`;
    default:
      return l.text;
  }
}

export default function EffectsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// effects"}</p>
        <h1>
          Motion that <em>earns its keep.</em>
        </h1>
        <p>
          The landing-page effects from digithings.ai and digiquant.io, gathered as living
          reference sections: the typed hero terminal, the scrolly module graph, the
          scroll-assembling research pipeline, and the ambient mesh bloom. Each section is one
          motion moment — reduced motion always gets the finished state, and the content still
          reads with scripts off.
        </p>
      </header>

      <section className="section-block" id="typed-terminal">
        <p className="kicker">{"// typed module terminal"}</p>
        <h2 className="title">The stack boots in front of you.</h2>
        <p className="section-copy">
          The digithings.ai hero signature: the landing terminal replays the boot transcript line
          by line with a blinking cursor — commands dwell longer than output, so the rhythm reads
          like a real shell. The component ships as <code>Terminal</code> in{" "}
          <code>@digithings/web</code>; the script here is the actual hero content. One motion
          moment, played once on load. Reduced motion renders the full transcript instantly and
          stills the cursor; without JavaScript a static transcript is served in its place.
        </p>
        <div className="fx-demo fx-term-demo">
          <div className="fx-term-live">
            <Terminal title="~/digithings — zsh" lines={BOOT} />
          </div>
          <noscript>
            <div className="term">
              <div className="term-bar">
                <i />
                <i />
                <i />
                <span className="term-title">~/digithings — zsh</span>
              </div>
              <pre className="term-body">{BOOT.map(plainLine).join("\n")}</pre>
            </div>
          </noscript>
        </div>
      </section>

      <section className="section-block" id="hero-graph">
        <p className="kicker">{"// cursor-follow graph"}</p>
        <h2 className="title">A field that reveals where you look.</h2>
        <p className="section-copy">
          The reveal-field graph from the digithings.ai and digiquant.io hero: a fixed field of
          nodes scattered across the surface, with the cursor as a lens — nearby nodes light up and
          web together while the trailing side dissolves, a faint ghost keeping a latent trace
          everywhere. It reads the live <code>--accent</code> token, so switching the theme or a
          livery re-dresses it; reduced motion paints one static centered frame. Move your cursor
          across the panel.
        </p>
        <div className="fx-demo hg-frame">
          <HeroGraphReference />
        </div>
      </section>

      <section className="section-block" id="module-graph">
        <p className="kicker">{"// scrolly module graph"}</p>
        <h2 className="title">Ten modules, walked one by one.</h2>
        <p className="section-copy">
          The digithings.ai convergence animation — the architecture story behind the hero. The
          graph pins to the viewport while scroll advances the focus node by node; incident edges
          light in accent, neighbours stay legible, everything else dims, and the side panel
          re-renders for the focused module. Hovering a node steals focus from the scroll; the
          right-edge rail ticks progress. Imported as <code>ScrollyGraph</code> from{" "}
          <code>@digithings/web</code> (styles in <code>web-theme.css</code>, data from the shared{" "}
          <code>modules</code> registry — the <code>man &lt;module&gt;</code> links resolve on
          digithings.ai). On narrow viewports or under reduced motion the pin is dropped entirely
          and the same content renders as a static stepper of module cards; without JavaScript the
          track collapses to one standing graph.
        </p>
        <div className="fx-demo">
          <ScrollyGraph />
        </div>
      </section>

      <section className="section-block accent-digiquant" id="research-pipeline">
        <p className="kicker">{"// digiquant research pipeline"}</p>
        <h2 className="title">Research in, orders out — assembled by scroll.</h2>
        <p className="section-copy">
          The scroll-assembling pipeline band from digiquant.io (<code>#pipeline</code>): seven
          stages slide in from alternating sides of a centre timeline as they enter the viewport,
          each docking against its rail dot, while the accent line fills with scroll progress —
          the same accent-bar language as the digiquant hero scroll cue. The final execution stage
          switches to the <code>--up</code> green: promotion past backtest is a human gate. This
          section wears <code>.accent-digiquant</code>, so every accent read is the teal livery.
          Reduced motion renders all steps in place with the timeline full; without JavaScript the
          assembled state is served.
        </p>
        <ResearchPipeline />
      </section>

      <section className="section-block" id="ambient-mesh">
        <p className="kicker">{"// ambient mesh"}</p>
        <h2 className="title">A bloom that never touches the copy.</h2>
        <p className="section-copy">
          The ambient background bloom from the digithings.ai subpages (architecture, chat,
          modules) — digiquant.io runs the same engine with a teal palette. Three blurred radial
          blobs drift on a canvas pinned behind the page top, reading their colour from the live{" "}
          <code>--ink</code> token: additive glow on dark, a soft gray wash on light. The blobs
          lean gently toward the pointer. On the live sites it covers the top 86svh of the page;
          here it is contained in a demo frame. Reduced motion paints one static frame — the drift
          never starts; the canvas is decorative (<code>aria-hidden</code>), so nothing is lost
          without it.
        </p>
        <div className="fx-demo fx-mesh-frame">
          <AmbientMesh />
          <p className="fx-mesh-label">content sits above the wash — z-index 1 over the canvas</p>
        </div>
      </section>

      <section className="section-block" id="section-morph">
        <p className="kicker">{"// section transition · zoom-morph"}</p>
        <h2 className="title">One section morphs into the next.</h2>
        <p className="section-copy">
          Mined from revolut.com&apos;s between-sections scroll: a full-bleed panel pins, then scales
          and rounds down into a docked card as the next section&apos;s copy rises in beside it — a
          continuous handoff rather than a cut. Scroll the panel below. Reduced motion renders the
          docked end state, un-pinned.
        </p>
        <SectionMorph />
      </section>

      <section className="section-block" id="stacking-panels">
        <p className="kicker">{"// section transition · stacking panels"}</p>
        <h2 className="title">Panels that stack as you go.</h2>
        <p className="section-copy">
          The layered variant: each panel pins, then the next slides up and over it — a rounded top
          edge and a cast shadow marking the seam — while the covered panel scales back and dims
          behind it. Scroll through the three below. Reduced motion renders a plain stack.
        </p>
        <StackingPanels />
      </section>

      <section className="section-block" id="crossfade-sections">
        <p className="kicker">{"// section transition · cross-fade + parallax"}</p>
        <h2 className="title">Sections that dissolve into each other.</h2>
        <p className="section-copy">
          The softest handoff: no pin — each block fades up as it nears the centre of the viewport
          and fades away as it leaves, its lines rising in at staggered parallax rates so one
          section melts into the next. Scroll through the three below. Reduced motion shows them all
          at rest.
        </p>
        <CrossfadeSections />
      </section>

      <RotatingPrompts />
      <ClipReveal />
    </main>
  );
}
