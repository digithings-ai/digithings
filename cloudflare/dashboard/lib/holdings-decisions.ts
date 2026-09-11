import type { TableRow } from '@/lib/database.types';

export type DecisionLogRow = TableRow<'decision_log'>;

export interface ProposedDecision {
  ticker: string;
  conviction: number | null;
  stance: string | null;
  runDate: string | null;
  node: string;
}

/** The Pipeline node (document_key) that explains a ticker's decision: its analyst memo. */
export function decisionNodeFor(ticker: string): string {
  return `analyst/${ticker.toUpperCase()}`;
}

/** Most-recent decision per ticker, keyed by uppercase ticker (latest run_date wins). */
export function latestDecisionByTicker(decisions: DecisionLogRow[]): Map<string, DecisionLogRow> {
  const m = new Map<string, DecisionLogRow>();
  for (const dec of decisions) {
    const t = String(dec.ticker || '').toUpperCase();
    if (!t) continue;
    const prev = m.get(t);
    if (!prev || String(dec.run_date || '') > String(prev.run_date || '')) m.set(t, dec);
  }
  return m;
}

/** Decision tickers the book does NOT hold — the "Proposed by the pipeline" shelf. */
export function proposedNotHeld(
  decisions: DecisionLogRow[],
  heldTickers: Set<string>
): ProposedDecision[] {
  const held = new Set([...heldTickers].map((t) => t.toUpperCase()));
  const latest = latestDecisionByTicker(decisions);
  const out: ProposedDecision[] = [];
  for (const [ticker, dec] of latest) {
    if (held.has(ticker)) continue;
    out.push({
      ticker,
      conviction: dec.conviction,
      stance: dec.stance ?? null,
      runDate: dec.run_date ?? null,
      node: decisionNodeFor(ticker),
    });
  }
  return out.sort(
    (a, b) =>
      String(b.runDate || '').localeCompare(String(a.runDate || '')) ||
      a.ticker.localeCompare(b.ticker)
  );
}
