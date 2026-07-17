/**
 * Conviction vocabulary — recorded faithfully from the olympus dashboard's shared
 * conviction primitives, RECORDED-FROM-OLYMPUS pending a promotion ruling: no
 * @digithings/web export exists yet, so this specimen reproduces the dress as
 * static markup sourced class-for-class from
 * `frontend/olympus/components/shared/conviction-meter.tsx` and
 * `signed-conviction-badge.tsx`, rather than consuming a shared primitive.
 *
 * THREE encodings, never conflated (the olympus F6 ruling) — same cyan
 * `--accent` pip grammar can mean two different things, and a signed badge
 * means a third; mixing them reads as one vocabulary when it is not:
 *
 * 1. Unsigned position meter — `ConvictionMeter`, integer 1–3 pips (max 3),
 *    clamped; filled pips are `--accent`, empty are `--hair`, and accent is
 *    the only color on the row (F5). Backs `positions.conviction` in the
 *    holdings table (AllocationsPositionsTable).
 * 2. Confidence pips — the SAME `ConvictionMeter` component re-scaled: a 0–1
 *    `theses.confidence` float rounded to 0–4 pips (max 4). Backs the thesis
 *    spine header (ThesisStoryCard) alongside its "NN% confidence" caption.
 * 3. Signed conviction badge — `SignedConvictionBadge`, a distinct component:
 *    a signed −5..+5 integer (`decision_log.conviction` /
 *    `AnalystPayload.conviction_score`), rendered verbatim and never clamped,
 *    up-toned at zero and above, down-toned below zero. Backs the dossier and
 *    decision log (TickerDossierView, ConvictionHistory) — and the holdings
 *    table's Decision column, in the same row as encoding 1's Conviction
 *    column (AllocationsPositionsTable's own header comment: "Ticker, Weight,
 *    Conviction, Day, Unrealized, Risk, Thesis, Decision, chevron"). The two
 *    are visual neighbors only below the `md` breakpoint, where the
 *    intervening Day/Unrealized/Risk/Thesis columns are responsive-hidden;
 *    at `md` and up those diagnostic columns render between them.
 *
 * That last pairing is why the rule matters: the holdings table renders an
 * unsigned position meter and a signed decision badge in the same row —
 * adjacent on narrow viewports, several diagnostic columns apart on desktop.
 * Either way they are not two views of one number — never merge them into
 * a single cell or a single scale.
 */

type PipDemo = { label: string; value: number; max: number; caption: string };

const POSITION_SAMPLES: PipDemo[] = [
  { label: "1 of 3", value: 1, max: 3, caption: "low conviction" },
  { label: "2 of 3", value: 2, max: 3, caption: "medium conviction" },
  { label: "3 of 3", value: 3, max: 3, caption: "high conviction" },
];

const CONFIDENCE_SAMPLES: PipDemo[] = [0, 0.25, 0.5, 0.75, 1].map((confidence) => ({
  label: `${Math.round(confidence * 100)}%`,
  value: Math.round(confidence * 4),
  max: 4,
  caption: `${Math.round(confidence * 100)}% confidence`,
}));

const SIGNED_SAMPLES = [-5, -3, -1, 0, 1, 3, 5];

/** Unexported: mirrors `ConvictionMeter` (conviction-meter.tsx) markup exactly,
 *  including the redundant `aria-label` + `sr-only` pair and `data-filled`
 *  attributes the source component ships for testability. */
function ConvictionPips({
  value,
  max,
  srLabel,
}: {
  value: number;
  max: number;
  srLabel: string;
}) {
  const filled = Math.max(0, Math.min(max, Math.round(value)));
  return (
    <span className="inline-flex items-center gap-1" role="img" aria-label={srLabel}>
      {Array.from({ length: max }).map((_, i) => {
        const isFilled = i < filled;
        return (
          <span
            key={i}
            data-filled={isFilled ? "true" : "false"}
            className={`h-1.5 w-1.5 rounded-full ${isFilled ? "bg-accent" : "bg-hair"}`}
          />
        );
      })}
      <span className="sr-only">{srLabel}</span>
    </span>
  );
}

/** Unexported: mirrors `SignedConvictionBadge` (signed-conviction-badge.tsx)
 *  markup exactly — sign is U+2212 minus, zero and above render up-toned. */
function ConvictionBadge({ value }: { value: number }) {
  const sign = value < 0 ? "−" : "+";
  const tone = value < 0 ? "text-down border-down/35" : "text-up border-up/35";
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums ${tone}`}
    >
      {sign}
      {Math.abs(value)}
    </span>
  );
}

export function ConvictionReference() {
  return (
    <section className="section-block" id="conviction">
      <p className="kicker">{"// conviction"}</p>
      <h2 className="title">One pip grammar. Three meanings — never one.</h2>
      <p className="section-copy">
        Recorded from the olympus dashboard&apos;s <code>ConvictionMeter</code> and{" "}
        <code>SignedConvictionBadge</code> — RECORDED-FROM-OLYMPUS, pending a promotion ruling.
        Not exported from <code>@digithings/web</code> yet, so this specimen reproduces the dress
        as static markup rather than consuming a shared primitive. Three distinct encodings share
        one cyan pip grammar plus one signed badge — the rule is that they never conflate.
      </p>

      <div className="cvx-block">
        <div className="cvx-scale">
          <p className="cvx-scale-label">{"// 1 — unsigned position meter · max 3 · holdings table"}</p>
          {POSITION_SAMPLES.map((s) => (
            <div className="cvx-row" key={s.label}>
              <span className="cvx-row-label">{s.label}</span>
              <ConvictionPips value={s.value} max={s.max} srLabel={`Conviction ${s.caption}`} />
              <span className="cvx-row-caption">{s.caption}</span>
            </div>
          ))}
          <div className="cvx-row">
            <span className="cvx-row-label">null</span>
            <span className="text-ink-mute">—</span>
            <span className="cvx-row-caption">no conviction recorded</span>
          </div>
        </div>

        <div className="cvx-scale">
          <p className="cvx-scale-label">{"// 2 — confidence pips · SAME meter, max 4 · thesis spine"}</p>
          {CONFIDENCE_SAMPLES.map((s) => (
            <div className="cvx-row" key={s.label}>
              <span className="cvx-row-label">{s.label}</span>
              <ConvictionPips value={s.value} max={s.max} srLabel={s.caption} />
              <span className="cvx-row-caption">{s.caption}</span>
            </div>
          ))}
        </div>

        <div className="cvx-scale">
          <p className="cvx-scale-label">
            {"// 3 — signed conviction badge · −5..+5, unclamped · dossier / decision log"}
          </p>
          <div className="cvx-badge-row">
            {SIGNED_SAMPLES.map((v) => (
              <ConvictionBadge key={v} value={v} />
            ))}
          </div>
        </div>
      </div>

      <div className="cvx-legend">
        <div className="cvx-legend-item">
          <span className="cvx-legend-num">1</span>
          <div>
            <p className="cvx-legend-title">Unsigned position meter</p>
            <p className="cvx-legend-copy">
              <code>positions.conviction</code> · 1–3 pips, clamped · holdings table
              (AllocationsPositionsTable)
            </p>
          </div>
        </div>
        <div className="cvx-legend-item">
          <span className="cvx-legend-num">2</span>
          <div>
            <p className="cvx-legend-title">Confidence pips</p>
            <p className="cvx-legend-copy">
              <code>theses.confidence</code> · 0–1 float → 0–4 pips · thesis spine
              (ThesisStoryCard)
            </p>
          </div>
        </div>
        <div className="cvx-legend-item">
          <span className="cvx-legend-num">3</span>
          <div>
            <p className="cvx-legend-title">Signed conviction badge</p>
            <p className="cvx-legend-copy">
              <code>decision_log.conviction</code> / <code>AnalystPayload.conviction_score</code> ·
              −5..+5, never clamped · dossier &amp; decision log (TickerDossierView,
              ConvictionHistory) and the holdings table&apos;s Decision column — same row as
              the Conviction meter, adjacent on mobile, columns apart on desktop
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
