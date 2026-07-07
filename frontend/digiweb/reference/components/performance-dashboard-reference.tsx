/**
 * Performance dashboard — the portfolio at a glance: a value/return headline,
 * a strip of aggregate ratios, and an allocation-by-strategy breakdown. Sits
 * above the single-strategy tearsheet metrics: this is the whole book. P&L
 * reads wear the money colors; ratios stay ink; the allocation bars take the
 * accent (teal on the digiquant-scoped Finance page). Static display template.
 */
const RATIOS = [
  { k: "sharpe", v: "2.31" },
  { k: "sortino", v: "3.10" },
  { k: "max drawdown", v: "−18.4%", tone: "down" },
  { k: "win rate", v: "58%" },
  { k: "profit factor", v: "2.31" },
  { k: "exposure", v: "0.62×" },
];

const ALLOC = [
  { name: "trend_xsec", pct: 42 },
  { name: "carry", pct: 28 },
  { name: "mean_rev", pct: 18 },
  { name: "pairs", pct: 12 },
];

export function PerformanceDashboardReference() {
  return (
    <section className="section-block" id="performance">
      <p className="kicker">{"// performance"}</p>
      <h2 className="title">The portfolio at a glance.</h2>
      <p className="section-copy">
        The book-level dashboard above the single-strategy tearsheet: headline value and return,
        the aggregate risk ratios, and where the capital actually sits. P&amp;L reads take the money
        colors; the allocation bars wear the accent.
      </p>

      {/* Migrated to token-backed utilities. The .pdash-ratio base class stays so
          its :first-child / :nth-child(4) border-left overrides (finance.css) keep
          matching. P&L reads wear text-up / text-down; alloc bars wear bg-accent. */}
      <div className="mt-[1.2rem] overflow-hidden rounded-[12px] border border-hair bg-surface">
        <div className="grid grid-cols-[1.4fr_1fr] max-[720px]:grid-cols-1">
          <div className="flex flex-col gap-[0.3rem] px-[1.4rem] pb-[1.2rem] pt-[1.4rem]">
            <span className="font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
              portfolio value
            </span>
            <span className="font-mono text-[clamp(1.6rem,4vw,2.2rem)] text-ink [font-variant-numeric:tabular-nums]">
              $1.284M
            </span>
            <span className="font-mono text-[0.72rem] text-up">+$5.47K · +0.43% today</span>
          </div>
          <div className="flex flex-col gap-[0.3rem] border-l border-hair px-[1.4rem] pb-[1.2rem] pt-[1.4rem] max-[720px]:border-l-0 max-[720px]:border-t max-[720px]:border-hair">
            <span className="font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
              total return
            </span>
            <span className="font-mono text-[clamp(1.6rem,4vw,2.2rem)] text-up [font-variant-numeric:tabular-nums]">
              +28.4%
            </span>
            <span className="font-mono text-[0.66rem] text-ink-mute">since inception · 2y</span>
          </div>
        </div>

        <div className="grid grid-cols-6 border-t border-hair max-[720px]:grid-cols-3">
          {RATIOS.map((r) => (
            <div key={r.k} className="pdash-ratio flex flex-col gap-[0.3rem] px-4 py-[0.9rem]">
              <span className="font-mono text-[0.52rem] uppercase tracking-[0.08em] text-ink-mute">
                {r.k}
              </span>
              <span
                className={`font-mono text-[0.98rem] [font-variant-numeric:tabular-nums] ${
                  r.tone === "down" ? "text-down" : "text-ink"
                }`}
              >
                {r.v}
              </span>
            </div>
          ))}
        </div>

        <div className="border-t border-hair px-[1.4rem] pb-[1.4rem] pt-[1.2rem]">
          <p className="mx-0 mb-[0.8rem] mt-0 font-mono text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">
            allocation by strategy
          </p>
          {ALLOC.map((a) => (
            <div
              key={a.name}
              className="grid grid-cols-[6rem_1fr_3rem] items-center gap-[0.9rem] py-[0.35rem] font-mono text-[0.78rem] text-ink-soft"
            >
              <span className="text-ink">{a.name}</span>
              <span className="h-2 overflow-hidden rounded-full bg-ink/[0.08]">
                <span
                  className="block h-full rounded-full bg-accent"
                  style={{ width: `${a.pct}%` }}
                />
              </span>
              <span className="text-right text-ink-soft [font-variant-numeric:tabular-nums]">
                {a.pct}%
              </span>
            </div>
          ))}
        </div>
      </div>
    </section>
  );
}
