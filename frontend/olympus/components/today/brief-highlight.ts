import type {
  ActionableItem,
  DashboardPositionEvent,
  RebalanceAction,
  RiskItem,
} from '@/lib/types';
import { isMaterialBookEvent } from '@/lib/brief-book-event';
import { resolvePmRationale } from '@/lib/pm-rationale';
import { buildPipelineHref } from '@/lib/pipeline-links';
import { ledgerHref, tickerDossierHref } from '@/lib/portfolio-url-state';

/**
 * Personal Morning Brief hero copy (variant B: research + portfolio dual beat).
 *
 * Assembled only from existing digest / rebalance / position-event fields —
 * no LLM calls, no invented metrics. Missing artifacts yield honest empty copy.
 */

export type BriefBeatKind = 'research' | 'portfolio' | 'watch';

export interface BriefBeat {
  kind: BriefBeatKind;
  label: string;
  text: string;
  /** False when the beat is an honest empty / degraded stand-in. */
  available: boolean;
  /** Sourced detail destination when the beat is available. */
  href?: string | null;
}

export interface BriefHighlight {
  /** Single glance sentence — most material finding or book action. */
  attention: string;
  /** Primary deep link for the attention claim. */
  attentionHref: string | null;
  /** Up to three beats: Research · Portfolio · Watch. */
  beats: BriefBeat[];
  /** True when at least one real pipeline artifact contributed copy. */
  hasPipelineSignal: boolean;
}

export interface BriefHighlightInput {
  headline: string | null;
  actions: RebalanceAction[];
  rationaleByTicker: Record<string, string>;
  actionables: ActionableItem[];
  risks: RiskItem[];
  contextBullets: string[];
  latestEvent: DashboardPositionEvent | null;
  /** Digest / research date for pipeline deep links. */
  digestDate?: string | null;
}

const MAX_LINE = 140;

function clip(text: string, max = MAX_LINE): string {
  const trimmed = text.replace(/\s+/g, ' ').trim();
  if (trimmed.length <= max) return trimmed;
  const cut = trimmed.slice(0, max - 1);
  const at = cut.lastIndexOf(' ');
  return `${(at > 40 ? cut.slice(0, at) : cut).trimEnd()}…`;
}

function titleCaseAction(action: string): string {
  const kind = action.trim().toUpperCase();
  if (!kind) return 'Adjust';
  return kind.charAt(0) + kind.slice(1).toLowerCase();
}

/** Non-HOLD book moves (EXIT at 0% current weight is a no-op). */
export function activeRebalanceActions(actions: RebalanceAction[]): RebalanceAction[] {
  return actions.filter((action) => {
    const kind = (action.action || '').trim().toUpperCase();
    return kind !== 'HOLD' && !(kind === 'EXIT' && (action.current_pct ?? 0) === 0);
  });
}

function rationaleFor(
  action: RebalanceAction,
  rationaleByTicker: Record<string, string>
): string | null {
  const key = action.ticker.trim().toUpperCase();
  // Never surface H8's mechanical sizing fallback as a "reason" — prefer real
  // PM thesis text already filtered into rationaleByTicker, else action+ticker only.
  return resolvePmRationale(action.rationale, rationaleByTicker[key]);
}

/** Compact book move — action + ticker (+ weight delta). No thesis prose. */
export function portfolioActionChip(action: RebalanceAction): string {
  const verb = titleCaseAction(action.action);
  const ticker = action.ticker.trim().toUpperCase();
  const from = action.current_pct;
  const to = action.recommended_pct;
  if (Number.isFinite(from) && Number.isFinite(to) && from !== to) {
    return clip(`${verb} ${ticker} (${from.toFixed(1)}% → ${to.toFixed(1)}%)`);
  }
  return clip(`${verb} ${ticker}`);
}

/** Full narrative move for the hero attention lead (thesis lives here once). */
function portfolioMoveLine(
  action: RebalanceAction,
  rationaleByTicker: Record<string, string>
): string {
  const verb = titleCaseAction(action.action);
  const ticker = action.ticker.trim().toUpperCase();
  const reason = rationaleFor(action, rationaleByTicker);
  if (reason) return clip(`${verb} ${ticker} — ${reason}`);
  return portfolioActionChip(action);
}

function eventLine(event: DashboardPositionEvent): string {
  const verb = titleCaseAction(event.event);
  const ticker = event.ticker.trim().toUpperCase();
  const reason = resolvePmRationale(event.reason);
  if (reason) return clip(`${verb} ${ticker} — ${reason}`);
  return clip(`${verb} ${ticker} recorded in the book ledger`);
}

function materialLatestEvent(
  event: DashboardPositionEvent | null
): DashboardPositionEvent | null {
  if (!event || !isMaterialBookEvent(event)) return null;
  return event;
}

function digestHref(date: string | null | undefined): string {
  return buildPipelineHref({ date: date ?? null, stage: 'synthesis', node: 'digest' });
}

function rebalanceHref(date: string | null | undefined): string {
  return buildPipelineHref({ date: date ?? null, stage: 'selection', node: 'pm-rebalance' });
}

function researchLine(input: BriefHighlightInput): BriefBeat {
  const href = digestHref(input.digestDate);
  const top = input.actionables[0];
  if (top?.label?.trim()) {
    const rationale = top.rationale?.trim();
    const text = rationale
      ? clip(`${top.label.trim()} — ${rationale}`)
      : clip(top.label.trim());
    return { kind: 'research', label: 'Research', text, available: true, href };
  }
  if (input.headline?.trim()) {
    return {
      kind: 'research',
      label: 'Research',
      text: clip(input.headline.trim()),
      available: true,
      href,
    };
  }
  const context = input.contextBullets.find((b) => b.trim());
  if (context) {
    return {
      kind: 'research',
      label: 'Research',
      text: clip(context.trim()),
      available: true,
      href,
    };
  }
  return {
    kind: 'research',
    label: 'Research',
    text: 'No research highlight was published for this run.',
    available: false,
    href: null,
  };
}

function portfolioLine(input: BriefHighlightInput): BriefBeat {
  const active = activeRebalanceActions(input.actions);
  if (active.length > 0) {
    const lead = active[0];
    const href = tickerDossierHref(lead.ticker);
    const first = portfolioActionChip(lead);
    if (active.length === 1) {
      return { kind: 'portfolio', label: 'Portfolio', text: first, available: true, href };
    }
    const rest = active
      .slice(1, 3)
      .map((a) => portfolioActionChip(a))
      .join(' · ');
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: clip(`${first} Also: ${rest}`),
      available: true,
      href,
    };
  }
  if (input.latestEvent && isMaterialBookEvent(input.latestEvent)) {
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: eventLine(input.latestEvent),
      available: true,
      href: ledgerHref({
        date: input.latestEvent.date,
        ticker: input.latestEvent.ticker,
      }),
    };
  }
  if (input.actions.length > 0) {
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: 'Holding the book — no allocation change recommended.',
      available: true,
      href: rebalanceHref(input.digestDate),
    };
  }
  return {
    kind: 'portfolio',
    label: 'Portfolio',
    text: 'No portfolio decision was published for this run.',
    available: false,
    href: null,
  };
}

function watchLine(input: BriefHighlightInput): BriefBeat {
  const thesesHref = '/portfolio?tab=theses';
  const risk = input.risks[0];
  if (risk?.label?.trim()) {
    const trigger = risk.trigger?.trim();
    const text = trigger
      ? clip(`${risk.label.trim()} — watch ${trigger}`)
      : clip(risk.label.trim());
    return { kind: 'watch', label: 'Watch', text, available: true, href: thesesHref };
  }
  const second = input.actionables[1];
  if (second?.label?.trim()) {
    return {
      kind: 'watch',
      label: 'Watch',
      text: clip(second.label.trim()),
      available: true,
      href: digestHref(input.digestDate),
    };
  }
  const context = input.contextBullets.find((b) => b.trim());
  if (context && input.actionables[0]?.label?.trim()) {
    return {
      kind: 'watch',
      label: 'Watch',
      text: clip(context.trim()),
      available: true,
      href: digestHref(input.digestDate),
    };
  }
  return {
    kind: 'watch',
    label: 'Watch',
    text: 'No watch item was published for this run.',
    available: false,
    href: null,
  };
}

function attentionSentence(input: BriefHighlightInput): { text: string; href: string | null } {
  const active = activeRebalanceActions(input.actions);
  if (active.length > 0) {
    return {
      text: portfolioMoveLine(active[0], input.rationaleByTicker),
      href: tickerDossierHref(active[0].ticker),
    };
  }
  const top = input.actionables[0];
  if (top?.label?.trim()) {
    const rationale = top.rationale?.trim();
    return {
      text: rationale
        ? clip(`${top.label.trim()} — ${rationale}`)
        : clip(top.label.trim()),
      href: digestHref(input.digestDate),
    };
  }
  if (input.headline?.trim()) {
    return { text: clip(input.headline.trim()), href: digestHref(input.digestDate) };
  }
  const latestMaterial = materialLatestEvent(input.latestEvent);
  if (latestMaterial) {
    return {
      text: eventLine(latestMaterial),
      href: ledgerHref({ date: latestMaterial.date, ticker: latestMaterial.ticker }),
    };
  }
  const risk = input.risks[0];
  if (risk?.label?.trim()) {
    return {
      text: clip(`Watch ${risk.label.trim()}`),
      href: '/portfolio?tab=theses',
    };
  }
  return { text: 'Nothing material was published for this run yet.', href: null };
}

/**
 * Build the personal Brief hero (variant B).
 * Always returns three beats so the layout stays stable when some are empty.
 */
export function buildBriefHighlight(input: BriefHighlightInput): BriefHighlight {
  const beats = [researchLine(input), portfolioLine(input), watchLine(input)];
  const hasPipelineSignal = beats.some((b) => b.available) || Boolean(input.headline?.trim());
  const attention = attentionSentence(input);
  return {
    attention: attention.text,
    attentionHref: attention.href,
    beats,
    hasPipelineSignal,
  };
}
