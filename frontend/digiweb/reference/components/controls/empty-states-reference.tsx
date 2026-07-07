/**
 * Empty / error states — the outcomes the skeleton loader resolves into when
 * there's nothing to show: no results, a first-run blank, and a load error.
 * Each is a centered card — glyph, title, one line of guidance, and the single
 * action that moves the user forward. Monochrome by default; the error reserves
 * the down colour. Static display templates.
 */
type EmptyState = {
  id: string;
  tone?: "error";
  icon: React.ReactNode;
  title: string;
  msg: string;
  action: string;
  primary?: boolean;
};

const STATES: EmptyState[] = [
  {
    id: "no-results",
    icon: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="M20 20l-3.5-3.5M8 11h6" strokeLinecap="round" />
      </>
    ),
    title: "No strategies match",
    msg: "Nothing fits those filters. Broaden the query or clear a tag or two.",
    action: "Clear filters",
  },
  {
    id: "first-run",
    icon: (
      <>
        <path d="M12 3v18M3 12h18" strokeLinecap="round" />
        <circle cx="12" cy="12" r="9" opacity="0.35" />
      </>
    ),
    title: "Nothing here yet",
    msg: "Run your first backtest and its tearsheet will land in the vault.",
    action: "New backtest",
    primary: true,
  },
  {
    id: "error",
    tone: "error",
    icon: (
      <>
        <path d="M12 3l9 16H3z" />
        <path d="M12 10v4M12 17v.5" strokeLinecap="round" />
      </>
    ),
    title: "Couldn't load positions",
    msg: "The venue feed timed out. Retry, or check the status page.",
    action: "Retry",
  },
];

export function EmptyStatesReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// empty & error states"}</p>
      <h2 className="title">When there&apos;s nothing to show.</h2>
      <p className="section-copy">
        The states the skeleton resolves into — no results, a first-run blank, a load error — each a
        centered card with a glyph, a title, one line of guidance, and the single action that moves
        forward. The error is the only one that spends the down color.
      </p>

      <div className="es-grid">
        {STATES.map((s) => (
          <article key={s.id} className={`es-card${s.tone === "error" ? " es-card--error" : ""}`}>
            <span className="es-icon" aria-hidden="true">
              <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinejoin="round">
                {s.icon}
              </svg>
            </span>
            <h3 className="es-title">{s.title}</h3>
            <p className="es-msg">{s.msg}</p>
            <button type="button" className={s.primary ? "btn-primary" : "btn-ghost"}>
              {s.action}
            </button>
          </article>
        ))}
      </div>
    </section>
  );
}
