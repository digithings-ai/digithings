import "./symbols.css";
import Image from "next/image";
import { Emblem, emblems, StackRow, type StackItem } from "@digithings/web";
import { Glyph, glyphNames } from "@/components/symbols/glyph";
import { OlympusMark, Wordmark } from "@/components/symbols/marks";

/* The full ICONS registry from frontend/web/src/components/logos.ts — every
   slug that resolves to a real Simple Icons mark in StackLogo. */
const REGISTRY_STACK: StackItem[] = [
  { name: "Drizzle", icon: "drizzle" },
  { name: "FastAPI", icon: "fastapi" },
  { name: "LangChain", icon: "langchain" },
  { name: "Next.js", icon: "nextdotjs" },
  { name: "OpenAI", icon: "openai" },
  { name: "OpenTelemetry", icon: "opentelemetry" },
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
  { name: "Optuna", icon: null, mono: "Op" },
];

/* QR favicon tiles. The digithings.ai and digiquant.io sets are distinct
   marks (different payloads and module shapes), so both ship. */
const QR_SETS = [
  {
    site: "digithings.ai",
    dark: [
      { src: "/favicon-qr.svg", label: "favicon-qr.svg" },
      { src: "/favicon-qr-mark-dark.svg", label: "favicon-qr-mark-dark.svg" },
    ],
    light: [
      { src: "/favicon-qr-light.svg", label: "favicon-qr-light.svg" },
      { src: "/favicon-qr-mark-light.svg", label: "favicon-qr-mark-light.svg" },
    ],
  },
  {
    site: "digiquant.io",
    dark: [
      { src: "/digiquant-favicon-qr.svg", label: "digiquant · favicon-qr.svg" },
      { src: "/digiquant-favicon-qr-mark-dark.svg", label: "digiquant · favicon-qr-mark-dark.svg" },
    ],
    light: [
      { src: "/digiquant-favicon-qr-light.svg", label: "digiquant · favicon-qr-light.svg" },
      {
        src: "/digiquant-favicon-qr-mark-light.svg",
        label: "digiquant · favicon-qr-mark-light.svg",
      },
    ],
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
          emblems, brand marks, QR tiles, vendor logos, and the utility glyph set — all drawn in
          currentColor so every mark inherits ink or accent from its livery scope.
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
          The text lockup follows the footer colophon grammar: mono at weight 500, prefix in ink,
          suffix wearing the accent of its scope. digichat has no separate mark — its module
          emblem is enough. The olympus mark is ported from the dashboard&apos;s loader, four
          strokes in currentColor.
        </p>
        <div className="sym-grid sym-grid--marks">
          <figure className="sym-cell sym-cell--mark">
            <Wordmark suffix="things" />
            <figcaption className="sym-label">digithings wordmark</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark accent-digiquant">
            <Wordmark suffix="quant" />
            <figcaption className="sym-label">digiquant wordmark</figcaption>
          </figure>
          <figure className="sym-cell sym-cell--mark">
            <span className="sym-mark">
              <OlympusMark size={40} />
            </span>
            <figcaption className="sym-label">olympus mark</figcaption>
          </figure>
        </div>
      </section>

      <section className="section-block" id="qr-marks">
        <p className="kicker">{"// qr marks"}</p>
        <h2 className="title">Favicons that scan.</h2>
        <p className="section-copy">
          Each site&apos;s favicon is a working QR code pointing at its own domain — the
          digithings.ai and digiquant.io sets are distinct marks, so both ship. Tile variants
          carry their own background; mark variants are transparent and sit on the surface behind
          them, one per theme.
        </p>
        {QR_SETS.map((set) => (
          <div key={set.site} className="sym-qr-set">
            <p className="sym-qr-site sym-label">{set.site}</p>
            <div className="sym-qr-row">
              <div className="sym-qr-card sym-qr-card--dark">
                {set.dark.map((qr) => (
                  <figure key={qr.src} className="sym-qr-item">
                    <Image src={qr.src} alt={`${set.site} QR mark, dark`} width={96} height={96} />
                    <figcaption className="sym-label">{qr.label}</figcaption>
                  </figure>
                ))}
              </div>
              <div className="sym-qr-card sym-qr-card--light">
                {set.light.map((qr) => (
                  <figure key={qr.src} className="sym-qr-item">
                    <Image
                      src={qr.src}
                      alt={`${set.site} QR mark, light`}
                      width={96}
                      height={96}
                    />
                    <figcaption className="sym-label">{qr.label}</figcaption>
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
