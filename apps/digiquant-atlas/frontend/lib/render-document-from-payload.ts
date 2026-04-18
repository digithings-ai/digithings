import { renderDigestMarkdownFromSnapshot, type DigestSnapshot } from './render-digest-from-snapshot';

function s(v: unknown): string {
  return v == null ? '' : String(v);
}

function asObj(v: unknown): Record<string, unknown> | null {
  return v && typeof v === 'object' && !Array.isArray(v) ? (v as Record<string, unknown>) : null;
}

function pushBulletBlock(target: string[], heading: string, items: unknown[] | undefined) {
  const arr = Array.isArray(items) ? items.filter((x) => s(x).trim()) : [];
  if (!arr.length) return;
  target.push(`### ${heading}`, '');
  for (const x of arr) target.push(`- ${s(x).trim()}`);
  target.push('');
}

export function renderDocumentMarkdownFromPayload(payload: unknown, documentKey?: string): string | null {
  const p = asObj(payload);
  if (!p) return null;

  // Back-compat: digest snapshot payload has no doc_type.
  if (p.regime || p.portfolio || p.sector_scorecard) {
    try {
      return renderDigestMarkdownFromSnapshot(payload as DigestSnapshot);
    } catch {
      /* noop */
    }
  }

  // Infer doc_type from document_key when it is missing (legacy/transitional payloads).
  let docType = s(p.doc_type);
  if (!docType && documentKey) {
    const dk = documentKey.toLowerCase();
    if (dk.startsWith('deliberation-transcript-index/')) docType = 'deliberation_session_index';
    else if (dk.startsWith('deliberation-transcript/')) docType = 'deliberation_transcript';
    else if (dk.startsWith('market-thesis-exploration/')) docType = 'market_thesis_exploration';
    else if (dk.startsWith('thesis-vehicle-map/')) docType = 'thesis_vehicle_map';
    else if (dk.startsWith('asset-recommendations/')) docType = 'asset_recommendation';
    else if (dk.startsWith('opportunity-screen/')) docType = 'opportunity_screen';
  }
  if (!docType) return null;

  const dateStr = s(p.date);

  if (docType === 'research_changelog') {
    const items = Array.isArray(p.items) ? p.items : [];
    const out: string[] = [`# Research changelog${dateStr ? ` — ${dateStr}` : ''}`, ''];
    for (const it of items) {
      const o = asObj(it);
      if (!o) continue;
      out.push(
        `- **${s(o.target_document_key)}** (${s(o.status)}): ${s(o.one_line_change)} _${s(o.severity)}_`
      );
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'research_baseline_manifest') {
    const docs = Array.isArray(p.documents) ? p.documents : [];
    const out: string[] = [`# Research baseline manifest${dateStr ? ` — ${dateStr}` : ''}`, ''];
    for (const row of docs) {
      const o = asObj(row);
      if (!o) continue;
      out.push(`- ${s(o.document_key)}${s(o.phase) ? ` (${s(o.phase)})` : ''}`);
    }
    if (s(p.prior_context_note).trim()) {
      out.push('', '## Prior context', s(p.prior_context_note).trim());
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'document_delta') {
    const out: string[] = [
      `# Document delta${dateStr ? ` — ${dateStr}` : ''}`,
      '',
      `**Target:** ${s(p.target_document_key)}`,
      `**Status:** ${s(p.status)}`,
    ];
    if (s(p.skip_reason).trim()) out.push(`**Skip reason:** ${s(p.skip_reason).trim()}`);
    const ops = Array.isArray(p.ops) ? p.ops : [];
    if (ops.length) {
      out.push('', '## Ops');
      for (const op of ops) {
        const o = asObj(op);
        if (!o) continue;
        out.push(`- \`${s(o.op)}\` ${s(o.path)}${s(o.reason) ? ` — ${s(o.reason)}` : ''}`);
      }
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'deep_dive') {
    const title = s(p.title) || 'Deep Dive';
    const body = asObj(p.body) || {};
    const md = s(body.markdown);
    if (md.trim()) return md.trimEnd() + '\n';
    return `# ${title}${dateStr ? ` — ${dateStr}` : ''}\n\n_No content available._\n`;
  }

  const lines: string[] = [];
  lines.push(`# ${docType.replace(/_/g, ' ').toUpperCase()}${dateStr ? ` — ${dateStr}` : ''}`);
  lines.push('');

  const body = asObj(p.body) || {};

  if (docType === 'weekly_digest') {
    lines.push('## Executive Summary');
    lines.push(s(body.executive_summary).trim());
    lines.push('');
    lines.push('## Key Takeaway');
    lines.push(s(body.key_takeaway).trim());
    lines.push('');
    return `${lines.join('\n').trim()}\n`;
  }

  if (docType === 'monthly_digest') {
    lines.push('## Month in Review');
    lines.push(s(body.month_in_review).trim());
    lines.push('');
    lines.push('## Key Learning');
    lines.push(s(body.key_learning).trim());
    lines.push('');
    return `${lines.join('\n').trim()}\n`;
  }

  if (docType === 'rebalance_decision') {
    lines.push('## PM Notes');
    lines.push(s(body.pm_notes).trim());
    lines.push('');
    const table = (body.rebalance_table as unknown[]) || [];
    if (Array.isArray(table) && table.length) {
      lines.push('## Rebalance Table');
      lines.push('| Ticker | Current% | Recommended% | Change | Action | Urgency | Rationale |');
      lines.push('|---|---:|---:|---:|---|---|---|');
      for (const row of table) {
        const r = asObj(row) || {};
        lines.push(
          `| ${s(r.ticker)} | ${s(r.current_pct)} | ${s(r.recommended_pct)} | ${s(r.change_pct)} | ${s(r.action)} | ${s(r.urgency)} | ${s(r.rationale)} |`
        );
      }
      lines.push('');
    }
    return `${lines.join('\n').trim()}\n`;
  }

  if (docType === 'market_thesis_exploration') {
    const b = asObj(p.body) || {};
    const out: string[] = [`# Market thesis exploration${dateStr ? ` — ${dateStr}` : ''}`, ''];
    const meta = asObj(p.meta);
    if (meta) {
      const refs = Array.isArray(meta.research_refs) ? meta.research_refs : [];
      if (refs.length) {
        out.push('## Research references', '');
        for (const r of refs) {
          const o = asObj(r);
          if (!o) continue;
          const sum = s(o.summary).trim();
          out.push(
            `- **${s(o.ref_kind)}** \`${s(o.ref_id)}\`${sum ? ` — ${sum}` : ''}`
          );
        }
        out.push('');
      }
    }
    const ed = s(b.executive_digest_pointer).trim();
    if (ed) {
      out.push('## Executive digest pointer', '', ed, '');
    }
    const dives = Array.isArray(b.deeper_dives) ? b.deeper_dives : [];
    if (dives.length) {
      out.push('## Deeper dives', '');
      dives.forEach((d, i) => {
        out.push(`### Dive ${i + 1}`, '', s(d).trim(), '');
      });
    }
    const theses = Array.isArray(b.theses) ? b.theses : [];
    for (const t of theses) {
      const th = asObj(t);
      if (!th) continue;
      out.push(`## ${s(th.thesis_id)} — ${s(th.title)}`, '');
      const bits = [
        s(th.direction) && `**Direction:** ${s(th.direction)}`,
        s(th.time_horizon) && `**Horizon:** ${s(th.time_horizon)}`,
        s(th.confidence) && `**Confidence:** ${s(th.confidence)}`,
      ].filter(Boolean);
      if (bits.length) out.push(bits.join(' · '), '');
      const stmt = s(th.statement).trim();
      if (stmt) {
        out.push('### Statement', '', stmt, '');
      }
      pushBulletBlock(out, 'Tailwinds', th.tailwinds as unknown[]);
      pushBulletBlock(out, 'Headwinds', th.headwinds as unknown[]);
      pushBulletBlock(out, 'Bull case', th.bull_case as unknown[]);
      pushBulletBlock(out, 'Bear case', th.bear_case as unknown[]);
      pushBulletBlock(out, 'Validation criteria', th.validation_criteria as unknown[]);
      pushBulletBlock(out, 'Invalidation criteria', th.invalidation_criteria as unknown[]);
      const linked = Array.isArray(th.linked_research_refs) ? th.linked_research_refs : [];
      if (linked.length) {
        out.push('### Linked research', '');
        for (const r of linked) {
          const o = asObj(r);
          if (!o) continue;
          out.push(`- **${s(o.ref_kind)}** \`${s(o.ref_id)}\``);
        }
        out.push('');
      }
      const subs = Array.isArray(th.sub_theses) ? th.sub_theses : [];
      for (const st of subs) {
        const sub = asObj(st);
        if (!sub) continue;
        out.push(`### Sub-thesis \`${s(sub.id)}\``, '', s(sub.claim).trim(), '');
        pushBulletBlock(out, 'Validation', sub.validation_criteria as unknown[]);
        pushBulletBlock(out, 'Invalidation', sub.invalidation_criteria as unknown[]);
      }
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'thesis_vehicle_map') {
    const b = asObj(p.body) || {};
    const meta = asObj(p.meta);
    const out: string[] = [`# Thesis → vehicle map${dateStr ? ` — ${dateStr}` : ''}`, ''];
    if (meta) {
      const sk = s(meta.source_exploration_key).trim();
      if (sk) out.push(`**Source exploration:** \`${sk}\``, '');
      const um = Array.isArray(meta.user_mandate_notes) ? meta.user_mandate_notes : [];
      pushBulletBlock(out, 'User mandate notes', um);
    }
    const mappings = Array.isArray(b.mappings) ? b.mappings : [];
    if (mappings.length) {
      out.push('## Mappings', '');
      out.push('| Thesis | Candidates | Rationale |');
      out.push('|---|---|---|');
      for (const row of mappings) {
        const m = asObj(row);
        if (!m) continue;
        const tickers = Array.isArray(m.candidate_tickers) ? m.candidate_tickers.map((x) => s(x)).join(', ') : '';
        const rat = s(m.rationale).replace(/\|/g, '\\|').replace(/\n/g, ' ');
        out.push(`| \`${s(m.thesis_id)}\` | ${tickers} | ${rat} |`);
      }
      out.push('');
      for (const row of mappings) {
        const m = asObj(row);
        if (!m) continue;
        pushBulletBlock(out, `Exclusions — ${s(m.thesis_id)}`, m.exclusion_reasons as unknown[]);
        pushBulletBlock(out, `Mandate notes — ${s(m.thesis_id)}`, m.user_mandate_notes as unknown[]);
      }
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'pm_allocation_memo') {
    const b = asObj(p.body) || {};
    const meta = asObj(p.meta);
    const out: string[] = [`# PM allocation memo${dateStr ? ` — ${dateStr}` : ''}`, ''];
    if (meta) {
      out.push(
        `**Prior snapshot (T−1):** ${s(meta.prior_snapshot_date)} · **Deliberation index:** ${s(meta.deliberation_index_key) || '—'} · **Session:** ${s(meta.session_id) || '—'}`,
        ''
      );
    }
    const nar = s(b.narrative).trim();
    if (nar) {
      out.push('## Narrative', '', nar, '');
    }
    const td = s(b.turnover_discipline).trim();
    if (td) {
      out.push('## Turnover discipline', '', td, '');
    }
    const tw = Array.isArray(b.target_weights_rationale) ? b.target_weights_rationale : [];
    if (tw.length) {
      out.push('## Target weights', '');
      out.push('| Ticker | Target % | Prior % | Rationale | Deliberation key |');
      out.push('|---:|---:|---:|---|---|');
      for (const row of tw) {
        const r = asObj(row);
        if (!r) continue;
        const rationale = s(r.rationale).replace(/\|/g, '\\|').replace(/\n/g, ' ');
        out.push(
          `| ${s(r.ticker)} | ${s(r.target_weight_pct)} | ${s(r.prior_weight_pct)} | ${rationale} | ${s(r.deliberation_document_key) || '—'} |`
        );
      }
      out.push('');
    }
    pushBulletBlock(out, 'Open questions', b.open_questions as unknown[]);
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'deliberation_session_index') {
    const b = asObj(p.body) || {};
    const meta = asObj(p.meta);
    const out: string[] = [`# Deliberation session index${dateStr ? ` — ${dateStr}` : ''}`, ''];
    if (meta) {
      const bits = [`**Session ID:** ${s(meta.session_id)}`, `**Kind:** ${s(meta.kind)}`];
      if (typeof meta.all_converged === 'boolean') bits.push(`**All converged:** ${meta.all_converged}`);
      out.push(bits.join(' · '), '');
    }
    const entries = Array.isArray(b.entries) ? b.entries : [];
    if (entries.length) {
      out.push('## Per-ticker sessions', '');
      out.push('| Ticker | Converged | Rounds | Document key |');
      out.push('|---|---:|---:|---|');
      for (const row of entries) {
        const e = asObj(row);
        if (!e) continue;
        out.push(
          `| ${s(e.ticker)} | ${e.converged === true ? 'Yes' : e.converged === false ? 'No' : '—'} | ${s(e.rounds_completed)} | \`${s(e.document_key)}\` |`
        );
      }
      out.push('');
    }
    const foot = s(b.footer_notes).trim();
    if (foot) out.push('## Notes', '', foot, '');
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'asset_recommendation') {
    const ticker = s(p.ticker);
    const meta = asObj(p.meta) || {};
    const b = asObj(p.body) || {};
    const out: string[] = [`# Asset recommendation — ${ticker || '—'}${dateStr ? ` — ${dateStr}` : ''}`, ''];
    const metaBits = [
      s(meta.name) && `**Name:** ${s(meta.name)}`,
      s(meta.category) && `**Category:** ${s(meta.category)}`,
      s(meta.analyst) && `**Analyst:** ${s(meta.analyst)}`,
      s(meta.thesis_id) && `**Thesis:** \`${s(meta.thesis_id)}\``,
      s(meta.regime) && `**Regime:** ${s(meta.regime)}`,
      meta.light_research_requested === true ? '**Light research requested:** yes' : '',
    ].filter(Boolean);
    if (metaBits.length) out.push(metaBits.join(' · '), '');
    const lt = Array.isArray(meta.linked_thesis_ids) ? meta.linked_thesis_ids : [];
    if (lt.length) {
      out.push('**Linked thesis IDs:** ' + lt.map((x) => `\`${s(x)}\``).join(', '), '');
    }
    const cites = Array.isArray(meta.research_citations) ? meta.research_citations : [];
    if (cites.length) {
      out.push('## Research citations', '');
      for (const c of cites) {
        const o = asObj(c);
        if (!o) continue;
        const note = s(o.note).trim();
        out.push(`- **${s(o.ref_kind)}** \`${s(o.ref_id)}\`${note ? ` — ${note}` : ''}`);
      }
      out.push('');
    }
    const ctx = asObj(b.context);
    if (ctx) {
      out.push(
        '## Context',
        '',
        `- **Price:** ${s(ctx.price)}`,
        `- **Day %:** ${s(ctx.day_pct)}`,
        `- **Segment bias:** ${s(ctx.segment_bias)}`,
        ''
      );
    }
    pushBulletBlock(out, 'Bull case', b.bull_case as unknown[]);
    pushBulletBlock(out, 'Bear case', b.bear_case as unknown[]);
    const v = asObj(b.verdict);
    if (v) {
      out.push('## Verdict', '');
      out.push(
        `- **Bias:** ${s(v.bias)}`,
        `- **Thesis status:** ${s(v.thesis_status)}`,
        `- **Recommended weight %:** ${s(v.recommended_weight_pct)}`,
        ''
      );
      const ent = s(v.entry).trim();
      const ex = s(v.exit).trim();
      if (ent) out.push(`**Entry:** ${ent}`, '');
      if (ex) out.push(`**Exit:** ${ex}`, '');
      const rat = s(v.rationale).trim();
      if (rat) out.push(rat, '');
    }
    return `${out.join('\n').trim()}\n`;
  }

  if (docType === 'deliberation_transcript') {
    const b = asObj(p.body) || {};
    const meta = asObj(p.meta);
    const tick = s(meta?.related_ticker);
    const out: string[] = [
      `# Deliberation transcript${tick ? ` — ${tick}` : ''}${dateStr ? ` — ${dateStr}` : ''}`,
      '',
    ];
    if (meta) {
      const bits = [`**Kind:** ${s(meta.kind)}`, `**Session:** ${s(meta.session_id) || '—'}`];
      if (typeof meta.converged === 'boolean') bits.push(`**Converged:** ${meta.converged}`);
      if (meta.delta_number != null) bits.push(`**Delta #:** ${s(meta.delta_number)}`);
      out.push(bits.join(' · '), '');
      const idx = s(meta.aggregate_index_document_key).trim();
      if (idx) out.push(`**Session index:** \`${idx}\``, '');
    }
    pushBulletBlock(out, 'Triggers', b.trigger_summary as unknown[]);
    const finals = Array.isArray(b.final_decisions) ? b.final_decisions : [];
    if (finals.length) {
      out.push('## Final decisions', '');
      for (const row of finals) {
        const r = asObj(row);
        if (!r) continue;
        out.push(`### ${s(r.ticker)}`, '');
        out.push('**Analyst**', '', s(r.analyst_recommendation).trim(), '');
        out.push('**PM**', '', s(r.pm_decision).trim(), '');
        const inv = s(r.invalidation_condition).trim();
        if (inv) out.push('**Invalidation**', '', inv, '');
      }
    }
    const rounds = Array.isArray(b.rounds) ? b.rounds : [];
    for (const round of rounds) {
      const ro = asObj(round);
      if (!ro) continue;
      out.push(`## ${s(ro.label)}`, '');
      const secs = Array.isArray(ro.sections) ? ro.sections : [];
      for (const sec of secs) {
        const se = asObj(sec);
        if (!se) continue;
        const h = s(se.heading).trim();
        if (h) out.push(`### ${h}`, '');
        const md = s(se.markdown).trim();
        if (md) out.push(md, '');
      }
    }
    const updates = Array.isArray(b.thesis_updates) ? b.thesis_updates : [];
    if (updates.length) {
      out.push('## Thesis updates', '');
      for (const row of updates) {
        const u = asObj(row);
        if (!u) continue;
        out.push(`- **${s(u.thesis_id)}** (${s(u.status)}): ${s(u.note).trim()}`);
      }
      out.push('');
    }
    const foot = s(b.footer_notes).trim();
    if (foot) out.push('## Notes', '', foot, '');
    return `${out.join('\n').trim()}\n`;
  }

  // Generic fallback: show body JSON for debugging rather than empty.
  lines.push('## Payload');
  try {
    lines.push('```json');
    lines.push(JSON.stringify(payload, null, 2));
    lines.push('```');
  } catch {
    lines.push('_Unable to render payload._');
  }
  lines.push('');
  return `${lines.join('\n').trim()}\n`;
}

