/**
 * F6 — the SIGNED stance badge: `decision_log.conviction` (−5..+5; maps to
 * AnalystPayload.conviction_score, ge=-5 le=5 — render any signed int, do NOT clamp).
 * up for a positive/neutral stance, down for negative — the strict
 * signed-financial-value semantic (F5). The only accent on its row.
 */
export function SignedConvictionBadge({ value }: { value: number }) {
  const sign = value < 0 ? '−' : '+';
  const tone = value < 0 ? 'text-down border-down/35' : 'text-up border-up/35';
  return (
    <span
      className={`inline-flex items-center rounded-md border px-1.5 py-0.5 font-mono text-[11px] font-semibold tabular-nums ${tone}`}
    >
      {sign}
      {Math.abs(value)}
    </span>
  );
}
