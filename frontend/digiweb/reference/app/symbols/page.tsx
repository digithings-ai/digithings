import "./symbols.css";
import Image from "next/image";
import { Emblem, emblems, StackRow, type StackItem } from "@digithings/web";
import { Glyph, glyphNames } from "@/components/symbols/glyph";
import { DigiquantMark, Wordmark } from "@/components/symbols/marks";
import {
  AnimatedLockup,
  HairlineWordmark,
  TerminalMark,
  TerminalWordmark,
} from "@/components/symbols/terminal-marks";

/* The full ICONS registry from frontend/digiweb/web/src/components/logos.ts — every
   slug that resolves to a real Simple Icons mark in StackLogo. */
const REGISTRY_STACK: StackItem[] = [
  { name: "Drizzle", icon: "drizzle" },
  { name: "FastAPI", icon: "fastapi" },
  { name: "LangChain", icon: "langchain" },
  { name: "Next.js", icon: "nextdotjs" },
  { name: "OpenAI", icon: "openai" },
  { name: "OpenTelemetry", icon: "opentelemetry" },
  { name: "Optuna", icon: "optuna" },
  { name: "Polars", icon: "polars" },
  { name: "PostgreSQL", icon: "postgresql" },
  { name: "Prometheus", icon: "prometheus" },
  { name: "Pydantic", icon: "pydantic" },
  { name: "React", icon: "react" },
  { name: "Redis", icon: "redis" },
  { name: "SQLite", icon: "sqlite" },
  { name: "Supabase", icon: "supabase" },
  { name: "Vercel", icon: "vercel" },
];

/* Names outside the registry — StackLogo degrades to a monogram chip. */
const FALLBACK_STACK: StackItem[] = [
  { name: "NautilusTrader", icon: null, mono: "NT" },
  { name: "LiteLLM", icon: null, mono: "LL" },
];

/* Brand favicon tiles. One artwork — the compact `d` + block cursor — in the two
   theme polarities, since the tile bakes its own background and cannot inherit
   ink. digithings.ai and digiquant.io ship byte-identical files (the mark is
   monochrome, so there is nothing site-specific to differ); both are listed
   because there is no build step syncing the three public/ directories. */
const TILE_SETS = [
  {
    site: "digithings.ai",
    dark: [{ src: "/favicon-dg-light.svg", label: "favicon-dg-light.svg" }],
    light: [{ src: "/favicon-dg.svg", label: "favicon-dg.svg" }],
  },
  {
    site: "digiquant.io",
    dark: [{ src: "/digiquant-favicon-dg-light.svg", label: "digiquant · favicon-dg-light.svg" }],
    light: [{ src: "/digiquant-favicon-dg.svg", label: "digiquant · favicon-dg.svg" }],
  },
];

export default function SymbolsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// symbols"}</p>
        <h1>
          Every mark, <em>one grammar.</em>
        </h1>
        <p>
          The complete symbol library across digithings.ai, digiquant.io, and the apps: module
          emblems, brand marks, favicon tiles, vendor logos, and the utility glyph set — nearly all
          drawn in currentColor so a mark inherits ink or accent from its livery scope (the terminal
          cut is the deliberate exception — see brand marks below).
        </p>
      </header>

      <section className="section-block" id="module-emblems">
        <p className="kicker">{"// module emblems"}</p>
        <h2 className="title">One geometric idea per module.</h2>
        <p className="section-copy">
          Each emblem is a single idea on a 32-grid — monoline, round caps, exactly one filled
          accent element. They draw in currentColor; the Emblem wrapper sets that to the
          module&apos;s own accent token, so the set stays cohesive while each mark carries its
          module&apos;s hue. Cells below wear their module&apos;s livery scope.
        </p>
        <div className="sym-grid">
          {Object.keys(emblems).map((id) => (
            <figure key={id} className={`sym-cell accent-${id}`}>
              <Emblem id={id} size={32} />
              <figcaption className="sym-label">{id}</figcaption>
            </figure>
          ))}
        </div>
      </section>

      <section className="section-block" id="brand-marks">
        <p className="kicker">{"// brand marks"}</p>
        <h2 className="title">Wordmarks and signature marks.</h2>
        <p className="section-copy">
          The house identity is a terminal line caught mid-prompt: the module name, then a filled
          block cursor. The cursor reuses the <code>.term-cursor</code> geometry — 0.6em wide,
          which is exactly one Geist Mono advance, so it fills one character cell. Two registers,
          each matching the weight of the surface it imitates: the <strong>terminal</strong> mark
          and wordmark at 400, the weight <code>.term-body</code> actually renders at, and the{" "}
          <strong>hairline</strong> display cut at 500, replicating the footer colophon. Each has a
          floor — the full <code>digi</code> lockup closes up below ~64px (use the compact{" "}
          <code>d</code> reduction), and the hairline is <strong>full-bleed only</strong>: its
          stroke scales with the art, so below an em of ~173px it goes sub-pixel. For{" "}
          <code>digithings</code>{" "}
          that is a ~1036px rendered width before the stroke reaches one device pixel — the
          colophon&apos;s own scale. The specimen below is deliberately the widest cell on the page
          and is <em>still</em>{" "}
          narrower than that, so treat it as a lockup check, not a fidelity one (each caption below
          repeats this so it reads next to the artifact, not just up here). The olympus mark is
          ported from the dashboard&apos;s loader, four strokes in currentColor. One exception to
          the currentColor rule: the <strong>terminal</strong> mark and wordmark are deliberately{" "}
          <strong>one tone</strong> — plain <code>--ink</code>, never <code>--accent</code>, even
          under a livery scope, because they read as a real shell prompt and{" "}
          <code>.term-body</code> itself never recolors by module. The specimen below wears{" "}
          <code>.accent-digiquant</code> anyway, on purpose, to show that side-by-side against the{" "}
          <strong>hairline</strong> cut, which genuinely does follow the scope.
        </p>
        <div className="sym-grid sym-grid--marks">
          <figure className="sym-cell sym-cell--mark">
            <span className="sym-mark">
              <TerminalMark size={44} />
            </span>
            <figcaption className="sym-label">terminal mark · full</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark">
            <span className="sym-mark">
              <TerminalMark size={44} variant="compact" />
            </span>
            <figcaption className="sym-label">terminal mark · compact</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark">
            <TerminalWordmark suffix="things" />
            <figcaption className="sym-label">terminal wordmark</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark accent-digiquant">
            <TerminalWordmark suffix="quant" />
            <figcaption className="sym-label">
              terminal wordmark · digiquant
              <span className="sym-note"> — one tone by design, ignores this scope</span>
            </figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark">
            <Wordmark suffix="things" />
            <figcaption className="sym-label">text wordmark (superseded)</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark">
            <span className="sym-mark">
              <DigiquantMark size={40} />
            </span>
            <figcaption className="sym-label">digiquant mark</figcaption>
          </figure>
        </div>
        <div className="sym-grid sym-grid--wide">
          <figure className="sym-cell sym-cell--wide">
            <AnimatedLockup className="block text-[2.6rem]" />
            <figcaption className="sym-label">
              animated lockup · types every module, pure CSS
            </figcaption>
          </figure>
          <figure className="sym-cell sym-cell--wide">
            <HairlineWordmark word="things" className="sym-hairline" />
            <figcaption className="sym-label">
              hairline wordmark · display only
              <span className="sym-note">
                {" "}
                — below its ~1036px floor here; a lockup check, not a fidelity one
              </span>
            </figcaption>
          </figure>
          <figure className="sym-cell sym-cell--wide accent-digiquant">
            <HairlineWordmark word="quant" className="sym-hairline sym-hairline--accent" />
            <figcaption className="sym-label">
              hairline wordmark · digiquant
              <span className="sym-note">
                {" "}
                — below its ~933px floor here; a lockup check, not a fidelity one
              </span>
            </figcaption>
          </figure>
        </div>
      </section>

      <section className="section-block" id="brand-tiles">
        <p className="kicker">{"// brand tiles"}</p>
        <h2 className="title">Favicons carry their own ink.</h2>
        <p className="section-copy">
          The favicon is the compact <code>d</code> + cursor reduction, never the full{" "}
          <code>digi</code> lockup — five character cells are illegible at 16px. A tile bakes its
          own background, so unlike every other mark here it cannot inherit ink from{" "}
          <code>currentColor</code>; each site therefore ships one file per theme polarity, wired
          through <code>metadata.icons</code> with <code>prefers-color-scheme</code> media queries.
          Those queries are the reason the sites do <em>not</em> use an{" "}
          <code>app/icon.svg</code>: the Next.js file convention overrides the metadata block and
          would silently drop them.
        </p>
        {TILE_SETS.map((set) => (
          <div key={set.site} className="sym-tile-set">
            <p className="sym-tile-site sym-label">{set.site}</p>
            <div className="sym-tile-row">
              <div className="sym-tile-card sym-tile-card--dark">
                {set.dark.map((tile) => (
                  <figure key={tile.src} className="sym-tile-item">
                    <Image src={tile.src} alt={`${set.site} favicon tile, dark`} width={96} height={96} />
                    <figcaption className="sym-label">{tile.label}</figcaption>
                  </figure>
                ))}
              </div>
              <div className="sym-tile-card sym-tile-card--light">
                {set.light.map((tile) => (
                  <figure key={tile.src} className="sym-tile-item">
                    <Image
                      src={tile.src}
                      alt={`${set.site} favicon tile, light`}
                      width={96}
                      height={96}
                    />
                    <figcaption className="sym-label">{tile.label}</figcaption>
                  </figure>
                ))}
              </div>
            </div>
          </div>
        ))}
      </section>

      <section className="section-block" id="vendor-logos">
        <p className="kicker">{"// vendor logos"}</p>
        <h2 className="title">Real marks, or an honest monogram.</h2>
        <p className="section-copy">
          Stack chips render the real vendor mark (Simple Icons, MIT data) tinted to ink-soft,
          brand colour on hover. A slug outside the registry never breaks the build — it degrades
          to a monogram chip, as the last three show.
        </p>
        <p className="sym-sublabel sym-label">registry marks</p>
        <StackRow items={REGISTRY_STACK} />
        <p className="sym-sublabel sym-label">monogram fallback</p>
        <StackRow items={FALLBACK_STACK} />
      </section>

      <section className="section-block" id="utility-glyphs">
        <p className="kicker">{"// utility glyphs"}</p>
        <h2 className="title">The interface symbol set.</h2>
        <p className="section-copy">
          Interface glyphs on a 24-grid: 1.5px monoline strokes with round caps, the GitHub mark
          as the official Simple Icons path. Everything renders in currentColor, so a glyph
          inherits ink in chrome and accent inside a livery scope.
        </p>
        <div className="sym-grid">
          {glyphNames.map((name) => (
            <figure key={name} className="sym-cell">
              <span className="sym-glyph">
                <Glyph name={name} size={24} />
              </span>
              <figcaption className="sym-label">{name}</figcaption>
            </figure>
          ))}
        </div>
      </section>
    </main>
  );
}
