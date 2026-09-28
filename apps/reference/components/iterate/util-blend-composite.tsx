"use client";

/**
 * Round-1 locked blend composite — one cohesive surface using the resolved
 * utilitarian-terminal rules from design/BLEND.md (not raw conflicting picks).
 * Gallery-only (`uv-` prefix).
 */
export function UtilBlendComposite() {
  return (
    <section className="uv-composite section-block" aria-label="Round 1 cohesive preview">
      <p className="kicker">{"// blend composite · round 1"}</p>
      <h2 className="title">One surface, resolved.</h2>
      <p className="section-copy">
        Your picks, after the consistency pass: zero radius, mono voice, white loud CTA, bracket
        docs, claim+install hero, sparse air, tonal slabs (soft fill without soft corners). This is
        the candidate default — poke holes before we touch <code>tokens.css</code>.
      </p>

      <div className="uv-comp">
        <header className="uv-comp-nav">
          <span className="uv-comp-brand">digithings</span>
          <a href="#docs">Docs</a>
          <a href="#pricing">Pricing</a>
          <button type="button" className="uv-comp-nav-fill">
            Login
          </button>
        </header>

        <div className="uv-comp-hero">
          <p className="uv-comp-kicker">{"// agent runtime"}</p>
          <h3 className="uv-comp-h">Run them anywhere. Leave them running.</h3>
          <p className="uv-comp-lede">
            Monochrome instrument chrome. One install command. Agents keep their terminals when the
            lid closes.
          </p>
          <div className="uv-comp-actions">
            <button type="button" className="uv-comp-cta">
              Start for free
            </button>
            <a className="uv-comp-docs" href="#docs">
              Docs
            </a>
          </div>
          <code className="uv-comp-curl">$ curl -fsSL https://example.com/install.sh | sh</code>
          <p className="uv-comp-meta">macOS · Linux · Windows · Apache-2.0</p>
        </div>

        <div className="uv-comp-stats" aria-label="Quiet stats">
          <div>
            <b>33k</b>
            <span>stars</span>
          </div>
          <div>
            <b>626k</b>
            <span>installs</span>
          </div>
          <div>
            <b>21</b>
            <span>agents</span>
          </div>
        </div>

        <div className="uv-comp-grid">
          <article className="uv-comp-slab">
            <p className="uv-comp-kicker">{"// surface"}</p>
            <h4>Tonal slab</h4>
            <p>
              `--surface` fill, hairline border, zero radius. Soft means value step — not roundness.
            </p>
          </article>
          <article className="uv-comp-slab">
            <p className="uv-comp-kicker">{"// input"}</p>
            <label className="uv-comp-field">
              <span>API key</span>
              <input readOnly defaultValue="dgk_live_…" />
            </label>
          </article>
          <article className="uv-comp-slab uv-comp-slab-term">
            <p className="uv-comp-kicker">{"// proof"}</p>
            <pre>
              {`❯ bun run dev
ready on http://127.0.0.1:4013
watching…`}
            </pre>
          </article>
        </div>
      </div>

      <ul className="uv-comp-rules">
        <li>
          <strong>Radius 0</strong> — controls, cards, inputs share one vocabulary.
        </li>
        <li>
          <strong>Mono all</strong> — hierarchy by size/tracking; serif is an escape hatch only.
        </li>
        <li>
          <strong>Loud = white rect</strong> — accent is for focus/live/identity, not the CTA fill.
        </li>
        <li>
          <strong>Sparse landings / instrument dashboards</strong> — same atoms, two densities.
        </li>
      </ul>
    </section>
  );
}
