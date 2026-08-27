import type {
  ActionableItem,
  DashboardPositionEvent,
  RebalanceAction,
  RiskItem,
} from '@/lib/types';

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
}

export interface BriefHighlight {
  /** Single glance sentence — most material finding or book action. */
  attention: string;
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
  const fromRow = typeof action.rationale === 'string' ? action.rationale.trim() : '';
  if (fromRow) return fromRow;
  const key = action.ticker.trim().toUpperCase();
  const mapped = rationaleByTicker[key]?.trim();
  return mapped || null;
}

function portfolioMoveLine(
  action: RebalanceAction,
  rationaleByTicker: Record<string, string>
): string {
  const verb = titleCaseAction(action.action);
  const ticker = action.ticker.trim().toUpperCase();
  const reason = rationaleFor(action, rationaleByTicker);
  if (reason) return clip(`${verb} ${ticker} — ${reason}`);
  const from = action.current_pct;
  const to = action.recommended_pct;
  if (Number.isFinite(from) && Number.isFinite(to) && from !== to) {
    return clip(`${verb} ${ticker} (${from.toFixed(1)}% → ${to.toFixed(1)}%)`);
  }
  return clip(`${verb} ${ticker}`);
}

function eventLine(event: DashboardPositionEvent): string {
  const verb = titleCaseAction(event.event);
  const ticker = event.ticker.trim().toUpperCase();
  if (event.reason?.trim()) return clip(`${verb} ${ticker} — ${event.reason.trim()}`);
  return clip(`${verb} ${ticker} recorded in the book ledger`);
}

function researchLine(input: BriefHighlightInput): BriefBeat {
  const top = input.actionables[0];
  if (top?.label?.trim()) {
    const rationale = top.rationale?.trim();
    const text = rationale
      ? clip(`${top.label.trim()} — ${rationale}`)
      : clip(top.label.trim());
    return { kind: 'research', label: 'Research', text, available: true };
  }
  if (input.headline?.trim()) {
    return {
      kind: 'research',
      label: 'Research',
      text: clip(input.headline.trim()),
      available: true,
    };
  }
  const context = input.contextBullets.find((b) => b.trim());
  if (context) {
    return {
      kind: 'research',
      label: 'Research',
      text: clip(context.trim()),
      available: true,
    };
  }
  return {
    kind: 'research',
    label: 'Research',
    text: 'No research highlight was published for this run.',
    available: false,
  };
}

function portfolioLine(input: BriefHighlightInput): BriefBeat {
  const active = activeRebalanceActions(input.actions);
  if (active.length > 0) {
    const first = portfolioMoveLine(active[0], input.rationaleByTicker);
    if (active.length === 1) {
      return { kind: 'portfolio', label: 'Portfolio', text: first, available: true };
    }
    const rest = active
      .slice(1, 3)
      .map((a) => `${titleCaseAction(a.action)} ${a.ticker.trim().toUpperCase()}`)
      .join(' · ');
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: clip(`${first} Also: ${rest}`),
      available: true,
    };
  }
  if (input.latestEvent && input.latestEvent.event !== 'HOLD') {
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: eventLine(input.latestEvent),
      available: true,
    };
  }
  if (input.actions.length > 0) {
    return {
      kind: 'portfolio',
      label: 'Portfolio',
      text: 'Holding the book — no allocation change recommended.',
      available: true,
    };
  }
  return {
    kind: 'portfolio',
    label: 'Portfolio',
    text: 'No portfolio decision was published for this run.',
    available: false,
  };
}

function watchLine(input: BriefHighlightInput): BriefBeat {
  const risk = input.risks[0];
  if (risk?.label?.trim()) {
    const trigger = risk.trigger?.trim();
    const text = trigger
      ? clip(`${risk.label.trim()} — watch ${trigger}`)
      : clip(risk.label.trim());
    return { kind: 'watch', label: 'Watch', text, available: true };
  }
  const second = input.actionables[1];
  if (second?.label?.trim()) {
    return {
      kind: 'watch',
      label: 'Watch',
      text: clip(second.label.trim()),
      available: true,
    };
  }
  const context = input.contextBullets.find((b) => b.trim());
  if (context && input.actionables[0]?.label?.trim()) {
    // Prefer context as watch when research already claimed the top actionable.
    return {
      kind: 'watch',
      label: 'Watch',
      text: clip(context.trim()),
      available: true,
    };
  }
  return {
    kind: 'watch',
    label: 'Watch',
    text: 'No watch item was published for this run.',
    available: false,
  };
}

function attentionSentence(input: BriefHighlightInput): string {
  const active = activeRebalanceActions(input.actions);
  if (active.length > 0) {
    return portfolioMoveLine(active[0], input.rationaleByTicker);
  }
  const top = input.actionables[0];
  if (top?.label?.trim()) {
    const rationale = top.rationale?.trim();
    return rationale
      ? clip(`${top.label.trim()} — ${rationale}`)
      : clip(top.label.trim());
  }
  if (input.headline?.trim()) {
    return clip(input.headline.trim());
  }
  if (input.latestEvent && input.latestEvent.event !== 'HOLD') {
    return eventLine(input.latestEvent);
  }
  const risk = input.risks[0];
  if (risk?.label?.trim()) {
    return clip(`Watch ${risk.label.trim()}`);
  }
  return 'Nothing material was published for this run yet.';
}

/**
 * Build the personal Brief hero (variant B).
 * Always returns three beats so the layout stays stable when some are empty.
 */
export function buildBriefHighlight(input: BriefHighlightInput): BriefHighlight {
  const beats = [researchLine(input), portfolioLine(input), watchLine(input)];
  const hasPipelineSignal = beats.some((b) => b.available) || Boolean(input.headline?.trim());
  return {
    attention: attentionSentence(input),
    beats,
    hasPipelineSignal,
  };
}
