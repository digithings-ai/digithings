/**
 * SignedConvictionBadge — the SIGNED stance badge, promoted from
 * `frontend/dashboard/components/shared/signed-conviction-badge.tsx`
 * (dashboard F6 ruling, logic verbatim): `decision_log.conviction`
 * (−5..+5; maps to `AnalystPayload.conviction_score`, ge=-5 le=5 — render
 * any signed int, do NOT clamp). Up-toned at zero and above, down-toned
 * below zero: the strict signed-financial-value semantic (F5), never to be
 * merged with the unsigned ConvictionMeter even when the two share a row.
 * One intentional deviation from the dashboard source: `rounded-none` pins
 * the utilitarian radius rule (visually no-op under preflight).
 *
 * Utility-classed (no family CSS); consuming apps need an `@source` line
 * for this directory (MIGRATION.md rule 3).
 */
export function SignedConvictionBadge({ value }: { value: number }) {
  const sign = value < 0 ? "−" : "+";
  const tone = value < 0 ? "text-down border-down/35" : "text-up border-up/35";
  return (
    <span
      className={`inline-flex items-center rounded-none border px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums ${tone}`}
    >
      {sign}
      {Math.abs(value)}
    </span>
  );
}
