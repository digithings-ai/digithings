/**
 * Markdown renderers for the payload shapes the Atlas/Hermes pipeline publishes
 * to Supabase (`documents.payload`, `daily_snapshots.snapshot`).
 *
 * The pipeline writes validated Pydantic payloads (SIMP-013) and leaves
 * `documents.content` empty, so the Research Library renders markdown from the
 * payload itself. Three shapes cover every pipeline document:
 *
 * - **Segment report** (`macro`, `bonds`, `equity`, `sector-*`, `alt-*`,
 *   `inst-*`, …): SegmentReport core (`segment`, `date`, `bias`, `headline`,
 *   `material_findings`, `sources`, `notes`) plus per-segment metric fields.
 * - **Master digest** (`digest-delta` / `digest-baseline` documents and the
 *   `daily_snapshots.snapshot` jsonb): {@link DigestPayload} shape.
 * - **PM rebalance** (`pm-rebalance`): `{ notes, actions, recommended_portfolio }`.
 *
 * All renderers are defensive: they tolerate missing/extra keys and never
 * throw on malformed payloads (worst case they render fewer sections).
 */

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function asObj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

/** "alt-cta-positioning" → "Alt CTA Positioning"-ish humanized heading. */
function humanize(slug: string): string {
  return slug
    .replace(/[-_]/g, ' ')
    .replace(/\b\w/g, (c) => c.toUpperCase())
    .replace(/\bCta\b/g, 'CTA')
    .replace(/\bVix\b/g, 'VIX')
    .replace(/\bEtf\b/g, 'ETF')
    .replace(/\bPm\b/g, 'PM')
    .replace(/\bUs\b/g, 'US')
    .replace(/\bAi\b/g, 'AI');
}

function escapeTableCell(v: unknown): string {
  return s(v).replace(/\|/g, '\\|').replace(/\n/g, ' ').trim();
}

/** Render an array of similarly-shaped objects as a compact markdown table. */
function objectArrayTable(rows: Record<string, unknown>[], maxCols = 7): string[] {
  const cols: string[] = [];
  for (const row of rows) {
    for (const k of Object.keys(row)) {
      if (!cols.includes(k)) cols.push(k);
      if (cols.length >= maxCols) break;
    }
    if (cols.length >= maxCols) break;
  }
  if (!cols.length) return [];
  const out: string[] = [];
  out.push(`| ${cols.map(humanize).join(' | ')} |`);
  out.push(`|${cols.map(() => '---').join('|')}|`);
  for (const row of rows) {
    out.push(`| ${cols.map((c) => escapeTableCell(row[c])).join(' | ')} |`);
  }
  out.push('');
  return out;
}

function pushFindings(out: string[], findings: unknown): void {
  if (!Array.isArray(findings) || !findings.length) return;
  out.push('## Material findings', '');
  for (const f of findings) {
    const o = asObj(f);
    if (!o) continue;
    const label = s(o.label).trim();
    const summary = s(o.summary).trim();
    if (!label && !summary) continue;
    out.push(`- **${label || 'Finding'}** — ${summary}`);
  }
  out.push('');
}

function pushSources(out: string[], sources: unknown): void {
  if (!Array.isArray(sources) || !sources.length) return;
  out.push('## Sources', '');
  for (const src of sources) {
    const o = asObj(src);
    if (!o) continue;
    const title = s(o.title).trim() || s(o.id).trim() || 'source';
    const url = s(o.url).trim();
    out.push(url ? `- [${title}](${url})` : `- ${title}`);
  }
  out.push('');
}

function pushNotes(out: string[], notes: unknown): void {
  const n = s(notes).trim();
  if (!n) return;
  out.push('## Notes', '', n, '');
}

/* ── Master digest ───────────────────────────────────────────────────────── */

/** SegmentReport-core keys handled explicitly by every renderer below. */
const CORE_KEYS = new Set([
  'segment',
  'date',
  'bias',
  'headline',
  'material_findings',
  'sources',
  'notes',
  'doc_type',
  'schema_version',
]);

const DIGEST_NARRATIVE_SECTIONS: Array<[key: string, heading: string]> = [
  ['us_equities_summary', 'US Equities'],
  ['asset_classes_summary', 'Asset Classes'],
  ['institutional_summary', 'Institutional'],
  ['alt_data_dashboard', 'Alt-Data Dashboard'],
  ['thesis_tracker', 'Thesis Tracker'],
  ['portfolio_recommendations', 'Portfolio Recommendations'],
];

/** True when a payload looks like the Phase-7 master digest (DigestPayload). */
export function isMasterDigestPayload(payload: unknown): boolean {
  const p = asObj(payload);
  if (!p) return false;
  if (typeof p.market_regime_snapshot === 'string') return true;
  if (asObj(p.segment_freshness)) return true;
  return s(p.segment) === 'master-digest' && typeof p.headline === 'string';
}

/** Markdown for the master-digest payload (documents and `daily_snapshots.snapshot`). */
export function renderMasterDigestMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const out: string[] = [];
  const date = s(p.date).trim();
  out.push(`# Daily Digest${date ? ` — ${date}` : ''}`, '');

  const regime = s(p.market_regime_snapshot).trim();
  const bias = s(p.bias).trim();
  if (regime || bias) {
    out.push('## Market regime', '');
    if (regime) out.push(regime, '');
    if (bias) out.push(`**Overall bias:** ${bias}`, '');
  }

  const headline = s(p.headline).trim();
  if (headline) out.push('## Headline', '', headline, '');

  const actionable = Array.isArray(p.actionable_summary) ? p.actionable_summary : [];
  if (actionable.length) {
    out.push('## Actionable summary', '');
    for (const a of actionable) {
      const o = asObj(a);
      if (o) {
        const pri = s(o.priority).trim();
        const label = s(o.label).trim() || 'Item';
        const rationale = s(o.rationale).trim();
        out.push(`- ${pri ? `**P${pri}** ` : ''}**${label}**${rationale ? ` — ${rationale}` : ''}`);
      } else if (s(a).trim()) {
        out.push(`- ${s(a).trim()}`);
      }
    }
    out.push('');
  }

  const risks = Array.isArray(p.risk_radar) ? p.risk_radar : [];
  if (risks.length) {
    out.push('## Risk radar', '');
    for (const r of risks) {
      const o = asObj(r);
      if (o) {
        const horizon = s(o.horizon_hours).trim();
        const trigger = s(o.trigger).trim();
        const label = s(o.label).trim() || 'Risk';
        out.push(
          `- **${label}**${trigger ? ` — ${trigger}` : ''}${horizon ? ` _(≤${horizon}h)_` : ''}`
        );
      } else if (s(r).trim()) {
        out.push(`- ${s(r).trim()}`);
      }
    }
    out.push('');
  }

  pushFindings(out, p.material_findings);

  for (const [key, heading] of DIGEST_NARRATIVE_SECTIONS) {
    const text = s(p[key]).trim();
    if (!text) continue;
    out.push(`## ${heading}`, '', text, '');
  }

  const freshness = asObj(p.segment_freshness);
  if (freshness && Object.keys(freshness).length) {
    out.push('## Segment freshness', '');
    out.push('| Segment | Source | As of |');
    out.push('|---|---|---|');
    for (const [seg, val] of Object.entries(freshness).sort(([a], [b]) => a.localeCompare(b))) {
      const o = asObj(val) ?? {};
      out.push(`| ${seg} | ${s(o.source)} | ${s(o.as_of)} |`);
    }
    out.push('');
  }

  pushNotes(out, p.notes);
  pushSources(out, p.sources);
  return `${out.join('\n').trim()}\n`;
}

/* ── PM rebalance ────────────────────────────────────────────────────────── */

/** True for the Hermes `pm-rebalance` payload (`{notes, actions, recommended_portfolio}`). */
export function isRebalancePayload(payload: unknown, documentKey?: string): boolean {
  if (documentKey === 'pm-rebalance') return true;
  const p = asObj(payload);
  if (!p) return false;
  return Array.isArray(p.actions) && Array.isArray(p.recommended_portfolio);
}

/** Markdown for the PM rebalance decision payload. */
export function renderRebalanceMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const out: string[] = ['# Rebalance Decision', ''];

  const actions = Array.isArray(p.actions)
    ? (p.actions.map(asObj).filter(Boolean) as Record<string, unknown>[])
    : [];
  if (actions.length) {
    out.push('## Actions', '', ...objectArrayTable(actions));
  }

  const rec = Array.isArray(p.recommended_portfolio)
    ? (p.recommended_portfolio.map(asObj).filter(Boolean) as Record<string, unknown>[])
    : [];
  if (rec.length) {
    out.push('## Recommended portfolio', '', ...objectArrayTable(rec));
  }

  if (!actions.length && !rec.length) {
    out.push('_No allocation changes were recommended for this run._', '');
  }

  pushNotes(out, p.notes);
  return `${out.join('\n').trim()}\n`;
}

/* ── Segment reports ─────────────────────────────────────────────────────── */

/** True for SegmentReport-shaped payloads (every Phase 1–6 research document). */
export function isSegmentReportPayload(payload: unknown): boolean {
  const p = asObj(payload);
  if (!p) return false;
  // The master digest extends the SegmentReport core — exclude it so each
  // sniffer is standalone-correct regardless of call order.
  if (isMasterDigestPayload(p)) return false;
  if (typeof p.segment !== 'string' || !p.segment) return false;
  return (
    typeof p.headline === 'string' ||
    typeof p.bias === 'string' ||
    Array.isArray(p.material_findings)
  );
}

/**
 * Markdown for a segment research report. Core narrative sections are rendered
 * explicitly; the segment-specific metric fields (e.g. `vix_level`,
 * `spy_trend`, `yield_curve_shape`) are rendered generically so new segments
 * display without frontend changes.
 */
export function renderSegmentReportMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const out: string[] = [];
  const date = s(p.date).trim();
  const segment = s(p.segment).trim();
  out.push(`# ${humanize(segment || 'Research Report')}${date ? ` — ${date}` : ''}`, '');

  const bias = s(p.bias).trim();
  if (bias) out.push(`**Bias:** ${bias}`, '');

  const headline = s(p.headline).trim();
  if (headline) out.push(headline, '');

  pushFindings(out, p.material_findings);

  // Generic rendering for segment-specific fields, grouped by value shape.
  const scalarLines: string[] = [];
  const extras = Object.entries(p)
    .filter(([k]) => !CORE_KEYS.has(k))
    .sort(([a], [b]) => a.localeCompare(b));
  for (const [key, value] of extras) {
    if (value == null) continue;
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      const text = s(value).trim();
      if (text) scalarLines.push(`- **${humanize(key)}:** ${text}`);
    }
  }
  if (scalarLines.length) {
    out.push('## Signals', '', ...scalarLines, '');
  }

  for (const [key, value] of extras) {
    if (Array.isArray(value) && value.length) {
      const objRows = value.map(asObj).filter(Boolean) as Record<string, unknown>[];
      out.push(`## ${humanize(key)}`, '');
      if (objRows.length === value.length) {
        out.push(...objectArrayTable(objRows));
      } else {
        for (const item of value) {
          const text = s(item).trim();
          if (text) out.push(`- ${text}`);
        }
        out.push('');
      }
      continue;
    }
    const o = asObj(value);
    if (o && Object.keys(o).length) {
      out.push(`## ${humanize(key)}`, '');
      for (const [ik, iv] of Object.entries(o)) {
        const text =
          typeof iv === 'string' || typeof iv === 'number' || typeof iv === 'boolean'
            ? s(iv).trim()
            : JSON.stringify(iv);
        if (text) out.push(`- **${humanize(ik)}:** ${text}`);
      }
      out.push('');
    }
  }

  pushNotes(out, p.notes);
  pushSources(out, p.sources);
  return `${out.join('\n').trim()}\n`;
}

/* ── Analyst specialist report (Phase 7C) ────────────────────────────────── */

/**
 * True for the Hermes per-ticker `SpecialistPayload` (`analyst/{ticker}`).
 * Real DB shape (documents.payload, 2026-06-17):
 *   { ticker, thesis, stance, conviction_score (integer), sources }
 * Requires conviction_score (integer) OR both stance AND thesis to distinguish
 * this shape from deliberation/{ticker} payloads that also carry a `ticker`.
 */
export function isAnalystSpecialistPayload(payload: unknown): boolean {
  const p = asObj(payload);
  if (!p) return false;
  if (typeof p.ticker !== 'string') return false;
  // Positive match on the real analyst shape: conviction_score is an integer
  // present only on SpecialistPayload (not on DebateSummary).
  if (typeof p.conviction_score === 'number') return true;
  // Fallback: must have both stance and thesis (DebateSummary has net_stance,
  // not stance, so this won't mis-route it).
  return typeof p.stance === 'string' && typeof p.thesis === 'string';
}

/** Markdown for a per-ticker analyst specialist report. */
export function renderAnalystSpecialistMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const ticker = s(p.ticker).trim();
  const date = s(p.date).trim();
  const out: string[] = [`# Analyst Report${ticker ? ` — ${ticker}` : ''}${date ? ` — ${date}` : ''}`, ''];

  const stance = s(p.stance).trim();
  // conviction_score is an integer in the real DB payload.
  const convictionScore =
    p.conviction_score != null && typeof p.conviction_score === 'number'
      ? String(p.conviction_score)
      : '';
  if (stance) {
    out.push(`**Stance:** ${stance}${convictionScore ? ` · **Conviction:** ${convictionScore}` : ''}`, '');
  }

  const thesis = s(p.thesis).trim();
  if (thesis) out.push('## Thesis', '', thesis, '');

  const sources = Array.isArray(p.sources) ? p.sources : [];
  if (sources.length) {
    pushSources(out, sources);
  }

  return `${out.join('\n').trim()}\n`;
}

/* ── Bull/bear debate (Phase 7CD) ─────────────────────────────────────────── */

/** True for the Hermes per-ticker `DebateSummary` payload (`deliberation/{ticker}`). */
export function isDebateSummaryPayload(payload: unknown): boolean {
  const p = asObj(payload);
  if (!p) return false;
  return (
    typeof p.bull_thesis === 'string' &&
    typeof p.bear_thesis === 'string' &&
    typeof p.net_stance === 'string'
  );
}

/** Markdown for a bull/bear debate summary (one ticker, N rounds). */
export function renderDebateSummaryMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const ticker = s(p.ticker).trim();
  const out: string[] = [`# Bull / Bear Debate${ticker ? ` — ${ticker}` : ''}`, ''];

  const stance = s(p.net_stance).trim();
  const delta = s(p.conviction_delta).trim();
  if (stance) {
    const sign = delta && !delta.startsWith('-') && delta !== '0' ? `+${delta}` : delta;
    out.push(`**Net stance:** ${stance}${delta ? ` · conviction Δ ${sign}` : ''}`, '');
  }

  const bull = s(p.bull_thesis).trim();
  const bear = s(p.bear_thesis).trim();
  if (bull) out.push('## Bull thesis', '', bull, '');
  if (bear) out.push('## Bear thesis', '', bear, '');

  const rounds = Array.isArray(p.rounds) ? p.rounds : [];
  if (rounds.length) {
    out.push('## Rounds', '');
    rounds.forEach((r, i) => {
      const o = asObj(r);
      if (!o) return;
      const n = s(o.round_number).trim();
      out.push(`### Round ${n || i + 1}`, '');
      const ba = s(o.bull_argument).trim();
      const be = s(o.bear_argument).trim();
      if (ba) out.push(`**Bull:** ${ba}`, '');
      if (be) out.push(`**Bear:** ${be}`, '');
    });
  }
  return `${out.join('\n').trim()}\n`;
}

/* ── Risk-temperament debate (Phase 7D) ───────────────────────────────────── */

/** True for the Hermes `RiskDebateSummary` payload (`risk-debate`). */
export function isRiskDebatePayload(payload: unknown): boolean {
  const p = asObj(payload);
  if (!p) return false;
  return (
    typeof p.aggressive_case === 'string' &&
    typeof p.conservative_case === 'string' &&
    typeof p.key_tension === 'string'
  );
}

/** Markdown for the aggressive-vs-conservative risk debate. */
export function renderRiskDebateMarkdown(payload: unknown): string {
  const p = asObj(payload) ?? {};
  const out: string[] = ['# Risk Temperament Debate', ''];
  const agg = s(p.aggressive_case).trim();
  const con = s(p.conservative_case).trim();
  const tension = s(p.key_tension).trim();
  if (agg) out.push('## Aggressive case', '', agg, '');
  if (con) out.push('## Conservative case', '', con, '');
  if (tension) out.push('## Key tension', '', tension, '');
  return `${out.join('\n').trim()}\n`;
}
