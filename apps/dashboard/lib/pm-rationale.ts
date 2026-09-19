/**
 * PM position rationale for Brief / actions UI.
 *
 * Historical `pm-rebalance` rows often carry the H8 mechanical fallback
 * ("Position weight set by deterministic risk sizing.") even when H7 already
 * published a real roster narrative. Never surface that boilerplate as a
 * "reason" — prefer usable PM thesis text, else show action + ticker only.
 *
 * Position-event rows written by execute_at_open's derived fallback also leak
 * engineering internals (`proposed_positions`, `rebalance_decision.json`) —
 * those never belong in desk copy either.
 */

const MECHANICAL_SIZING_RE =
  /^(position\s+)?weight\s+set\s+by\s+deterministic\s+risk\s+sizing\.?$/i;

/** execute_at_open / backfill prose that names pipeline artifacts. */
const DERIVED_BOOK_REASON_RE =
  /derived from positions book|proposed_positions|rebalance_decision\.json|digest (proposed_positions )?unavailable/i;

/** True when the string is empty or the known H8 sizing fallback (and close variants). */
export function isMechanicalSizingRationale(raw: string | null | undefined): boolean {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t) return true;
  return MECHANICAL_SIZING_RE.test(t);
}

/** True when the string is execute_at_open derived-fallback engineering copy. */
export function isDerivedBookReason(raw: string | null | undefined): boolean {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t) return false;
  return DERIVED_BOOK_REASON_RE.test(t);
}

/** Return trimmed rationale, or null when empty / non-desk boilerplate. */
export function usablePmRationale(raw: string | null | undefined): string | null {
  const t = (raw ?? '').replace(/\s+/g, ' ').trim();
  if (!t || isMechanicalSizingRationale(t) || isDerivedBookReason(t)) return null;
  return t;
}

/**
 * First usable PM reason among candidates (action row → map → H7 → H6 → H5).
 * Matches the backend priority in H8 `_selection_rationale_by_ticker`, minus the
 * mechanical fallback — callers must not invent a reason when this returns null.
 */
export function resolvePmRationale(
  ...candidates: Array<string | null | undefined>
): string | null {
  for (const c of candidates) {
    const usable = usablePmRationale(c);
    if (usable) return usable;
  }
  return null;
}

/** Extract H7 roster narratives from a `pm-direction-memo` document payload. */
export function narrativesFromPmDirectionMemo(
  memo: Record<string, unknown> | null | undefined
): Record<string, string> {
  const out: Record<string, string> = {};
  if (!memo) return out;
  const roster = memo.roster;
  if (!Array.isArray(roster)) return out;
  for (const row of roster) {
    if (!row || typeof row !== 'object') continue;
    const r = row as { ticker?: unknown; narrative?: unknown };
    if (typeof r.ticker !== 'string' || !r.ticker.trim()) continue;
    const narrative = usablePmRationale(
      typeof r.narrative === 'string' ? r.narrative : null
    );
    if (!narrative) continue;
    out[r.ticker.trim().toUpperCase()] = narrative;
  }
  return out;
}

/**
 * Build the Brief/actions rationale map: prefer real PM text over H8 fallback.
 *
 * Order per ticker: usable `pm-rebalance` action rationale → H7 roster narrative
 * → optional extras (deliberation conclusion, thesis). Mechanical strings never
 * enter the map.
 */
export function buildDisplayRationaleByTicker(input: {
  pmRebalanceActions?: unknown;
  pmDirectionMemo?: Record<string, unknown> | null;
  extrasByTicker?: Record<string, string>;
}): Record<string, string> {
  const fromRebalance: Record<string, string> = {};
  if (Array.isArray(input.pmRebalanceActions)) {
    for (const row of input.pmRebalanceActions) {
      if (!row || typeof row !== 'object') continue;
      const r = row as { ticker?: unknown; rationale?: unknown };
      if (typeof r.ticker !== 'string' || !r.ticker.trim()) continue;
      const rationale = usablePmRationale(
        typeof r.rationale === 'string' ? r.rationale : null
      );
      if (!rationale) continue;
      fromRebalance[r.ticker.trim().toUpperCase()] = rationale;
    }
  }

  const fromH7 = narrativesFromPmDirectionMemo(input.pmDirectionMemo);
  const extras = input.extrasByTicker ?? {};
  const keys = new Set([
    ...Object.keys(fromRebalance),
    ...Object.keys(fromH7),
    ...Object.keys(extras),
  ]);

  const out: Record<string, string> = {};
  for (const key of keys) {
    const resolved = resolvePmRationale(fromRebalance[key], fromH7[key], extras[key]);
    if (resolved) out[key] = resolved;
  }
  return out;
}
