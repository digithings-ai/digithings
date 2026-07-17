/**
 * Thesis story spine — the position → stock → macro chain rendered as a
 * story-first accordion on the Portfolio "Theses" tab (#1562).
 *
 * The hierarchy is derived from the `thesis_vehicles` map (ticker → MARKET
 * thesis_id, with rationale + candidate_rank), NOT `theses.linked_market_thesis_id`
 * (which is self-referential / dead — see the #1562 blueprint). Because
 * `thesis_vehicles.thesis_id` is co-generated per `date` with the `theses` table
 * (the slug churns daily), the join is reliable *within a date*; `selectThesisAsOf`
 * therefore picks the latest date (≤ anchor) that carries a mapping for a given
 * thesis and tags the block with that source date.
 *
 * Three conviction encodings stay strictly separate (never conflated):
 *   - positions.conviction 1–3  → ConvictionMeter max=3
 *   - theses.confidence 0–1      → ConvictionMeter 4-pip
 *   - decision_log.conviction / analyst conviction_score (signed) → SignedConvictionBadge
 *
 * These functions are pure and unit-tested; the query wiring lives in
 * `lib/queries.ts` (`fetchThesisVehicleMap`).
 */
import type { Position, Thesis } from './types';
import { normalizeThesisId, thesisIdEquals } from './thesis-id';
import { sortByConfidenceDesc } from './theses-ledger';
import { decisionNodeFor, type DecisionLogRow, type ProposedDecision } from './holdings-decisions';

/**
 * Demo anchor date. On this date the `theses` table is dense (19 market views)
 * and `thesis_vehicles` wires a full hierarchy, so a reviewer sees the story
 * fully populated. Gated behind `selectThesisAsOf` / `buildThesisStory`'s
 * `anchorDate` option so PRODUCTION stays on latest-available-per-entity.
 */
export const DEMO_THESIS_ANCHOR_DATE = '2026-07-12';

/** A ticker → MARKET-thesis mapping row from `thesis_vehicles` (the reliable join). */
export interface ThesisVehicleRow {
  date: string;
  /** MARKET thesis id (matches `theses.thesis_id` on the same date). */
  thesisId: string;
  ticker: string;
  rationale: string | null;
  candidateRank: number | null;
}

/** Level-2/3 node: one vehicle expressing a market thesis + its stock-level story. */
export interface VehicleExpression {
  ticker: string;
  /** The analyst's reason this vehicle expresses the view (thesis_vehicles.rationale,
   *  falling back to the vehicle thesis's notes when absent). */
  rationale: string | null;
  candidateRank: number | null;
  /** Held position, when the book holds this ticker; null for proposed-only vehicles. */
  position: Position | null;
  /** Latest signed analyst call for this ticker (decision_log, latest run_date). */
  latestDecision: DecisionLogRow | null;
}

/** Level-1 node: one market thesis + the vehicles that express it. */
export interface ThesisStory {
  thesis: Thesis;
  vehicles: VehicleExpression[];
  /** Source date of the vehicle rows shown (for the per-block AsOfBadge). */
  asOf: string | null;
}

/** The two honest trailing buckets. */
export interface UnassignedGroup {
  /** Held tickers not expressed by any currently-shown market thesis. */
  heldUnmapped: Position[];
  /** Vehicles the spine proposes that the book does not hold. */
  proposedUnheld: ProposedDecision[];
}

export interface ThesisStoryResult {
  stories: ThesisStory[];
  unassigned: UnassignedGroup;
  /** Vehicle rows actually shown across the spine (for weight attribution). */
  effectiveRows: ThesisVehicleRow[];
}

/**
 * Pick the vehicle rows for one market thesis "as of" the anchor:
 * the most recent date **≤ anchorDate** that carries a mapping for `thesisId`
 * (or the overall most recent such date when none fall on/before the anchor —
 * the anchor is a soft ceiling). Rows are returned rank-then-ticker ordered,
 * with the source `asOf` date for the block's AsOfBadge.
 */
export function selectThesisAsOf(
  rows: ThesisVehicleRow[],
  thesisId: string,
  anchorDate: string | null
): { rows: ThesisVehicleRow[]; asOf: string | null } {
  const matching = rows.filter((r) => thesisIdEquals(r.thesisId, thesisId));
  if (matching.length === 0) return { rows: [], asOf: null };
  const eligible = anchorDate ? matching.filter((r) => r.date <= anchorDate) : matching;
  const pool = eligible.length > 0 ? eligible : matching;
  const asOf = pool.reduce<string | null>((m, r) => (m === null || r.date > m ? r.date : m), null);
  const selected = pool
    .filter((r) => r.date === asOf)
    .sort(
      (a, b) =>
        (a.candidateRank ?? Number.MAX_SAFE_INTEGER) - (b.candidateRank ?? Number.MAX_SAFE_INTEGER) ||
        a.ticker.localeCompare(b.ticker)
    );
  return { rows: selected, asOf };
}

/**
 * Attribute each held ticker's book weight to its PRIMARY market thesis only —
 * the mapping with the lowest `candidate_rank` (ties → lexical `thesis_id`).
 * A ticker is NEVER summed into more than one thesis, so a many-to-many ticker
 * (e.g. CPER under two views) does not double-count the book. Keyed by
 * normalized thesis id.
 */
export function attributeWeightToPrimaryThesis(
  positions: Position[],
  thesisVehicleRows: ThesisVehicleRow[]
): Map<string, number> {
  const heldWeight = new Map<string, number>();
  for (const p of positions) heldWeight.set(p.ticker.toUpperCase(), p.weight_actual ?? 0);

  const byTicker = new Map<string, ThesisVehicleRow[]>();
  for (const r of thesisVehicleRows) {
    const t = r.ticker.toUpperCase();
    if (!heldWeight.has(t)) continue;
    const list = byTicker.get(t);
    if (list) list.push(r);
    else byTicker.set(t, [r]);
  }

  const out = new Map<string, number>();
  for (const [ticker, group] of byTicker) {
    const primary = [...group].sort(
      (a, b) =>
        (a.candidateRank ?? Number.MAX_SAFE_INTEGER) - (b.candidateRank ?? Number.MAX_SAFE_INTEGER) ||
        a.thesisId.localeCompare(b.thesisId)
    )[0];
    if (!primary) continue;
    const key = normalizeThesisId(primary.thesisId);
    out.set(key, (out.get(key) ?? 0) + (heldWeight.get(ticker) ?? 0));
  }
  return out;
}

/**
 * Assemble the story tree from market theses + the vehicle map + held positions +
 * latest decisions. Replaces the broken `groupVehicleTheses` (which keyed on the
 * dead `linked_market_thesis_id`).
 *
 * @param opts.anchorDate  Date ceiling for vehicle-row selection (pass
 *   `DEMO_THESIS_ANCHOR_DATE` for the dense demo; omit / null for latest-available).
 * @param opts.vehicleTheses  Vehicle-kind theses, used only as a rationale fallback.
 */
export function buildThesisStory(
  marketTheses: Thesis[],
  thesisVehicleRows: ThesisVehicleRow[],
  positions: Position[],
  decisionsByTicker: Map<string, DecisionLogRow>,
  opts?: { anchorDate?: string | null; vehicleTheses?: Thesis[] }
): ThesisStoryResult {
  const anchorDate = opts?.anchorDate ?? null;
  const sortedMarket = sortByConfidenceDesc(marketTheses);
  const positionByTicker = new Map(positions.map((p) => [p.ticker.toUpperCase(), p]));

  // Rationale fallback: a `vehicle-{ticker}` thesis's notes, when thesis_vehicles.rationale is null.
  const vehicleNotesByTicker = new Map<string, string>();
  for (const v of opts?.vehicleTheses ?? []) {
    const t = normalizeThesisId(v.id); // 'vehicle-ewt' → 'EWT'
    if (t && v.notes) vehicleNotesByTicker.set(t, v.notes);
  }

  const stories: ThesisStory[] = [];
  const effectiveRows: ThesisVehicleRow[] = [];
  const shownTickers = new Set<string>(); // tickers expressed under some CURRENT thesis

  for (const thesis of sortedMarket) {
    const { rows, asOf } = selectThesisAsOf(thesisVehicleRows, thesis.id, anchorDate);
    const vehicles: VehicleExpression[] = rows.map((r) => {
      const t = r.ticker.toUpperCase();
      shownTickers.add(t);
      effectiveRows.push(r);
      return {
        ticker: t,
        rationale: r.rationale ?? vehicleNotesByTicker.get(t) ?? null,
        candidateRank: r.candidateRank,
        position: positionByTicker.get(t) ?? null,
        latestDecision: decisionsByTicker.get(t) ?? null,
      };
    });
    stories.push({ thesis, vehicles, asOf });
  }

  // Bucket 1 — held, not tied to any currently-shown market view.
  //
  // NB (deviation from the blueprint's literal "no thesis_vehicles row on ANY date"):
  // thesis_vehicles.thesis_id churns daily, so a held ticker mapped under a
  // now-defunct id would be "ever-mapped" yet attach to NO current spine thesis —
  // the literal rule would then hide the entire held book, defeating the blueprint's
  // own goal ("the held book always renders fully"). We therefore surface held
  // tickers absent from the CURRENT spine, which renders the book honestly.
  const heldUnmapped = positions
    .filter((p) => p.ticker.toUpperCase() !== 'CASH')
    .filter((p) => !shownTickers.has(p.ticker.toUpperCase()))
    .sort((a, b) => (b.weight_actual ?? 0) - (a.weight_actual ?? 0));

  // Bucket 2 — vehicles the spine proposes that the book does not hold.
  const heldSet = new Set(positions.map((p) => p.ticker.toUpperCase()));
  const seen = new Set<string>();
  const proposedUnheld: ProposedDecision[] = [];
  for (const r of effectiveRows) {
    const t = r.ticker.toUpperCase();
    if (heldSet.has(t) || seen.has(t)) continue;
    seen.add(t);
    const dec = decisionsByTicker.get(t) ?? null;
    proposedUnheld.push({
      ticker: t,
      conviction: dec?.conviction ?? null,
      stance: dec?.stance ?? null,
      runDate: dec?.run_date ?? null,
      node: decisionNodeFor(t),
    });
  }
  proposedUnheld.sort((a, b) => a.ticker.localeCompare(b.ticker));

  return { stories, unassigned: { heldUnmapped, proposedUnheld }, effectiveRows };
}
