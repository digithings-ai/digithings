/**
 * Code review — a unified diff inside a document frame, the proof surface behind
 * an agentic-coding stack. Added and removed lines are pastel washes: the third
 * color domain, deliberately never the saturated up/down money hues, which stay
 * reserved for P&L. Mono throughout, with a line gutter and a review status.
 * Static data — a display template, no diffing engine.
 */
type Line =
  | { kind: "ctx"; old: number; now: number; text: string }
  | { kind: "add"; now: number; text: string }
  | { kind: "del"; old: number; text: string };

// A realistic quant change: capping position size at a Kelly fraction.
const HUNK: Line[] = [
  { kind: "ctx", old: 41, now: 41, text: "    def size(self, signal: float, equity: float) -> float:" },
  { kind: "ctx", old: 42, now: 42, text: '        """Target notional for this bar."""' },
  { kind: "del", old: 43, text: "        return equity * signal * self.leverage" },
  { kind: "add", now: 43, text: "        raw = equity * signal * self.leverage" },
  { kind: "add", now: 44, text: "        cap = equity * self.kelly_cap" },
  { kind: "add", now: 45, text: "        return min(raw, cap)" },
  { kind: "ctx", old: 44, now: 46, text: "" },
  { kind: "ctx", old: 45, now: 47, text: "    def flat(self) -> bool:" },
];

export function CodeReviewReference() {
  const added = HUNK.filter((l) => l.kind === "add").length;
  const removed = HUNK.filter((l) => l.kind === "del").length;

  return (
    <section className="section-block code-review">
      <p className="kicker">{"// code review"}</p>
      <h2 className="title">Diffs, the third color domain.</h2>
      <p className="section-copy">
        The review surface — the proof behind an agentic-coding stack. Added and removed lines are
        <b> pastel washes</b> inside a document frame, a domain of their own: never the saturated{" "}
        <code>--up</code>/<code>--down</code> money hues, which stay reserved for P&amp;L. Mono
        throughout, a line gutter, and a status the reviewer can trust.
      </p>

      <article className="rv-frame">
        <header className="flex items-center justify-between gap-[0.8rem] border-b border-hair px-[1rem] py-[0.7rem] font-mono text-[0.72rem]">
          <span className="text-ink">digiquant/src/strategy/trend_xsec.py</span>
          <span className="inline-flex items-center gap-[0.6rem] text-[0.68rem]">
            <span className="rv-add-count">+{added}</span>
            <span className="rv-del-count">−{removed}</span>
            <span className="rv-chip">changes requested</span>
          </span>
        </header>
        <div className="rv-diff" role="table" aria-label="Unified diff">
          {HUNK.map((l, i) => (
            <div key={i} className={`rv-row rv-${l.kind}`} role="row">
              <span className="rv-ln" role="cell">
                {l.kind === "add" ? "" : l.old}
              </span>
              <span className="rv-ln" role="cell">
                {l.kind === "del" ? "" : l.now}
              </span>
              <span className="rv-mark" aria-hidden="true">
                {l.kind === "add" ? "+" : l.kind === "del" ? "−" : " "}
              </span>
              <code className="rv-code" role="cell">
                {l.text || " "}
              </code>
            </div>
          ))}
        </div>
      </article>
    </section>
  );
}
