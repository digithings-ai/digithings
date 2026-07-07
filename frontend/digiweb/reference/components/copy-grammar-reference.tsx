type Formula = { pattern: string; example: string; ours?: boolean };

const HEADLINES: Formula[] = [
  { pattern: "[era] + [category]", example: "The next generation of code review." },
  { pattern: "[product] is [role] for [ambition]", example: "Cursor is your coding agent for building ambitious software." },
  { pattern: "[quality] + [category] for [outcome]", example: "Frontier AI models for everything you build." },
  { pattern: "ours", example: "A quant hedge fund. In a box you own.", ours: true },
];

const CTAS: { theirs: string; ours: string }[] = [
  { theirs: "Download for macOS", ours: "git clone · docker compose" },
  { theirs: "Get API key", ours: "make stack-local · issue a key" },
  { theirs: "Get started", ours: "ask digichat · open olympus" },
  { theirs: "Start free trial", ours: "run a backtest" },
  { theirs: "Explore / Contact sales", ours: "read docs · contact@digithings.ai" },
];

const DOCTRINE: { label: string; value: string }[] = [
  { label: "voice", value: "Technical, precise, ownership-oriented — infrastructure, not consumer warmth." },
  { label: "naming", value: "every module and sub-graph is lowercase (digithings · digiquant · digichat · atlas · hermes · kairos · olympus); capitals are reserved for third-party tools (NautilusTrader, LangGraph)." },
  { label: "social proof", value: "{NN}% + label, or {Org} × digiquant — real numbers and real orgs only." },
];

export function CopyGrammarReference() {
  return (
    <section className="section-block copy-grammar">
      <p className="kicker">{"// copy & voice"}</p>
      <h2 className="title">Literal verbs, owned voice.</h2>
      <p className="section-copy">
        The words are part of the design system. Headlines follow a formula, CTAs name their
        destination, and the voice stays technical and ownership-oriented — closer to an
        infrastructure vendor than a consumer app.
      </p>

      <div className="cg-grid">
        <div className="cg-card">
          <p className="cg-card-title">Headline formulas</p>
          <dl className="cg-list">
            {HEADLINES.map((h) => (
              <div key={h.example} className={h.ours ? "cg-row cg-ours" : "cg-row"}>
                <dt>{h.pattern}</dt>
                <dd>{h.example}</dd>
              </div>
            ))}
          </dl>
        </div>

        <div className="cg-card">
          <p className="cg-card-title">CTAs name the destination</p>
          <dl className="cg-list">
            {CTAS.map((c) => (
              <div key={c.theirs} className="cg-row">
                <dt>{c.theirs}</dt>
                <dd>
                  <span className="cg-arrow" aria-hidden="true">
                    →{" "}
                  </span>
                  {c.ours}
                </dd>
              </div>
            ))}
          </dl>
          <p className="cg-note">
            Never &ldquo;Get started&rdquo; without naming where it goes. Per-tier verbs escalate
            with commitment: sign up → get started → start free trial → request a demo.
          </p>
        </div>

        <div className="cg-card cg-card--wide">
          <p className="cg-card-title">Voice doctrine</p>
          <dl className="cg-list cg-list--doctrine">
            {DOCTRINE.map((d) => (
              <div key={d.label} className="cg-row">
                <dt>{d.label}</dt>
                <dd>{d.value}</dd>
              </div>
            ))}
          </dl>
        </div>
      </div>
    </section>
  );
}
