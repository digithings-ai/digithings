import "./foundations.css";
import { designTokens } from "@digithings/design/tokens";

/**
 * Foundations — the language's roles, read from the generated token table.
 *
 * `designTokens` is generated from `packages/design/tokens.css`, so this page
 * cannot disagree with the shipped values: a token change reaches it without
 * an edit here. Both themes are shown side by side because the role, not the
 * hex, is the contract.
 */

const THEMES = ["dark", "light"] as const;

type ThemeName = (typeof THEMES)[number];

type Tone = { hex?: string; r?: number; g?: number; b?: number; a?: number };

function colour(theme: ThemeName, token: string): string {
  const tone = (designTokens[theme] as Record<string, Tone>)[token];
  if (!tone) return "transparent";
  if (tone.hex) return tone.hex;
  if (tone.r !== undefined) return `rgba(${tone.r}, ${tone.g ?? 0}, ${tone.b ?? 0}, ${tone.a ?? 1})`;
  return "transparent";
}

const LIVERIES = Object.keys(designTokens.dark).filter((token) => token.startsWith("accent-"));

const GROUPS: readonly { name: string; note: string; tokens: readonly string[] }[] = [
  {
    name: "ground",
    note: "Page, slab, nested slab. Tonal steps only.",
    tokens: ["bg", "surface", "surface-2"],
  },
  {
    name: "line",
    note: "The only depth cue. 1px, never 2px.",
    tokens: ["hair", "hair-2", "hair-strong"],
  },
  {
    name: "ink",
    note: "Primary text, body, meta.",
    tokens: ["ink", "ink-soft", "ink-mute"],
  },
  {
    name: "signal",
    note: "Focus, live/selected, chart identity, livery default.",
    tokens: ["accent", "accent-weak", "on-accent"],
  },
  {
    name: "money & state",
    note: "Signed P&L and non-financial failure. Never decorative.",
    tokens: [
      "up",
      "down",
      "warn",
      "danger",
      "status-open",
      "status-add",
      "status-trim",
      "status-exit",
      "status-closed",
    ],
  },
  {
    name: "terminal",
    note: "The diegetic surface family.",
    tokens: ["term-bg", "term-ink", "term-mute", "term-hair", "term-fill"],
  },
  {
    name: "heat",
    note: "Contrast-on-heatmap ink, for returns matrices.",
    tokens: ["heat-ink", "heat-ink-strong"],
  },
];

const TYPE_LADDER: readonly { token: string; label: string }[] = [
  { token: "--type-hero", label: "hero" },
  { token: "--type-display", label: "display" },
  { token: "--type-page-title", label: "page title" },
  { token: "--type-section", label: "section" },
  { token: "--type-section-stand", label: "section standfirst" },
  { token: "--type-body", label: "body" },
  { token: "--type-meta", label: "meta" },
  { token: "--type-sub-label", label: "sub-label" },
];

const RULES: readonly string[] = [
  "Zero radius. Corners are square unless the kit part says otherwise.",
  "One hairline for depth. Shadows are not part of the language.",
  "Mono for meta, labels and numbers; display and body carry prose.",
  "Signal is earned: accent marks focus, selection and livery — never decoration.",
  "Money colours mean signed P&L. State colours mean failure.",
  "Motion is a build, not a bounce: stepped, interruptible, reduced-motion aware.",
];

export default function FoundationsPage() {
  return (
    <main className="reference-page">
      <header className="hero">
        <p className="kicker">{"// foundations"}</p>
        <h1>
          Roles before <em>hexes.</em>
        </h1>
        <p>
          Every value below is generated from <code>packages/design/tokens.css</code> into{" "}
          <code>designTokens</code>. The table is the shipped palette, not a sample: dark and light
          are the same roles in two polarities.
        </p>
      </header>

      <section className="section-block">
        <h2 className="title">Palette roles</h2>
        <div className="fd-groups">
          {GROUPS.map((group) => (
            <section className="fd-group" key={group.name}>
              <div className="fd-group-head">
                <h3>{group.name}</h3>
                <p>{group.note}</p>
              </div>
              <table className="fd-table">
                <thead>
                  <tr>
                    <th scope="col">token</th>
                    <th scope="col">dark</th>
                    <th scope="col">light</th>
                  </tr>
                </thead>
                <tbody>
                  {group.tokens.map((token) => (
                    <tr key={token}>
                      <th scope="row">--{token}</th>
                      {THEMES.map((theme) => (
                        <td key={theme}>
                          <span
                            className="fd-swatch"
                            style={{ background: colour(theme, token) }}
                            aria-hidden="true"
                          />
                          <code>{colour(theme, token)}</code>
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </section>
          ))}

          <section className="fd-group">
            <div className="fd-group-head">
              <h3>liveries</h3>
              <p>One accent per module, applied with the matching scope class.</p>
            </div>
            <ul className="fd-liveries">
              {LIVERIES.map((token) => (
                <li key={token}>
                  <span
                    className="fd-swatch"
                    style={{ background: colour("dark", token) }}
                    aria-hidden="true"
                  />
                  <span>--{token}</span>
                  <code>{colour("dark", token)}</code>
                </li>
              ))}
            </ul>
          </section>
        </div>
      </section>

      <section className="section-block">
        <h2 className="title">Type</h2>
        <p className="section-copy">
          The scale is tokenised; the faces are display, body and mono. The top bar&apos;s type
          suite picker swaps the family set live, which is the cheapest way to see whether a
          composition depends on one typeface.
        </p>
        <div className="fd-type">
          {TYPE_LADDER.map((step) => (
            <div className="fd-type-row" key={step.token}>
              <code className="fd-type-token">{step.token}</code>
              <p style={{ fontSize: `var(${step.token})` }}>
                Drill, don&apos;t decorate. {step.label}.
              </p>
            </div>
          ))}
        </div>
      </section>

      <section className="section-block">
        <h2 className="title">Rules</h2>
        <ol className="fd-rules">
          {RULES.map((rule) => (
            <li key={rule}>{rule}</li>
          ))}
        </ol>
      </section>
    </main>
  );
}
