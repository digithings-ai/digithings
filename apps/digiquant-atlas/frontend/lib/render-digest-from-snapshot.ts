/**
 * Client-side markdown compiled from a digest snapshot JSON (v1).
 * Kept in sync with scripts/materialize_snapshot.py `render_digest_markdown`.
 */

export type DigestSnapshot = {
  date?: string;
  regime?: Record<string, unknown>;
  portfolio?: Record<string, unknown>;
  actionable?: string[];
  risks?: string[];
  sector_scorecard?: Array<Record<string, unknown>>;
  narrative?: Record<string, unknown>;
};

function str(v: unknown): string {
  return v == null ? '' : String(v);
}

export function renderDigestMarkdownFromSnapshot(snapshot: DigestSnapshot): string {
  const date = str(snapshot.date);
  const regime = (snapshot.regime || {}) as Record<string, unknown>;
  const lines: string[] = [];

  lines.push(`# DIGEST — ${date}`);
  lines.push('');
  lines.push('## Market Regime Snapshot');
  lines.push(`**Overall Bias**: ${str(regime.bias)}\n`);
  const dom = regime.dominant_force;
  if (dom) lines.push(`- **Dominant force**: ${str(dom)}`);
  lines.push(`- **Label**: ${str(regime.label)}`);
  lines.push(`- **Conviction**: ${str(regime.conviction)}`);
  lines.push('');
  if (regime.summary) {
    lines.push(str(regime.summary));
    lines.push('');
  }

  lines.push('## Actionable Summary');
  for (const item of (snapshot.actionable || []).slice(0, 10)) {
    lines.push(`- ${item}`);
  }
  lines.push('');

  lines.push('## Risk Radar');
  for (const item of (snapshot.risks || []).slice(0, 10)) {
    lines.push(`- ${item}`);
  }
  lines.push('');

  lines.push('## Sector Scorecard');
  lines.push('| Sector | ETF | Bias | Confidence | Key Driver |');
  lines.push('|---|---|---|---|---|');
  for (const row of snapshot.sector_scorecard || []) {
    const r = row as Record<string, unknown>;
    lines.push(
      `| ${str(r.sector)} | ${str(r.etf)} | ${str(r.bias)} | ${str(r.confidence)} | ${str(r.key_driver)} |`
    );
  }
  lines.push('');

  const nar = snapshot.narrative;
  if (nar && typeof nar === 'object') {
    lines.push('## Narrative');
    lines.push('');
    // Research segments (always rendered when present)
    for (const key of ['alt_data', 'institutional', 'macro', 'us_equities']) {
      const val = (nar as Record<string, unknown>)[key];
      if (val) {
        const title = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        lines.push(`### ${title}`);
        lines.push(String(val).trim());
        lines.push('');
      }
    }
    const ac = (nar as Record<string, unknown>).asset_classes;
    if (ac && typeof ac === 'object') {
      const o = ac as Record<string, unknown>;
      if (['bonds', 'commodities', 'forex', 'crypto', 'international'].some((k) => o[k])) {
        lines.push('### Asset Classes');
        for (const k of ['bonds', 'commodities', 'forex', 'crypto', 'international']) {
          const v = o[k];
          if (v) {
            lines.push(`#### ${k.charAt(0).toUpperCase() + k.slice(1)}`);
            lines.push(String(v).trim());
            lines.push('');
          }
        }
      }
    }
    // PM sections (only rendered when present — Track B populates these)
    for (const key of ['thesis_tracker', 'portfolio_recs']) {
      const val = (nar as Record<string, unknown>)[key];
      if (val) {
        const title = key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase());
        lines.push(`### ${title}`);
        lines.push(String(val).trim());
        lines.push('');
      }
    }
  }

  // Portfolio positioning — only shown when Track B has populated it
  const portfolio = snapshot.portfolio as Record<string, unknown> | undefined;
  if (portfolio && (portfolio.posture || (portfolio.positions as unknown[])?.length)) {
    lines.push('## Portfolio Positioning');
    lines.push(`**Portfolio Posture**: ${str(portfolio.posture)}`);
    if (portfolio.cash_pct != null) lines.push(`**Cash %**: ${str(portfolio.cash_pct)}`);
    lines.push('');
    lines.push('| Ticker | Weight% | Action | Rationale |');
    lines.push('|---|---:|---|---|');
    const positions = (portfolio.positions || []) as Array<Record<string, unknown>>;
    for (const p of positions) {
      lines.push(
        `| ${str(p.ticker)} | ${str(p.weight_pct)} | ${str(p.action)} | ${str(p.rationale)} |`
      );
    }
    lines.push('');
  }

  return `${lines.join('\n').trim()}\n`;
}
