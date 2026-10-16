'use client';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@digithings/ui/ui';
import { SafeMarkdown } from '@/components/SafeMarkdown';

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function cell(value: unknown): string {
  if (vEmpty(value)) return '—';
  return String(value);
}

function vEmpty(value: unknown): boolean {
  return value == null || value === '';
}

export default function InputsDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  const body = asRecord(payload);
  if (!body) {
    return <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>;
  }

  const watchlist = Array.isArray(body.watchlist)
    ? body.watchlist.map((item) => String(item)).filter(Boolean)
    : [];
  const profile = asRecord(body.profile) ?? {};
  const market = asRecord(body.market_data) ?? {};
  const prior = asRecord(body.prior_context) ?? {};
  const gap = Array.isArray(market.price_basket_gap)
    ? market.price_basket_gap.map((item) => String(item)).filter(Boolean)
    : [];

  const rows: [string, string][] = [
    ['Watchlist', watchlist.join(', ') || '—'],
    ['Profile pin', cell(profile.profile_config_version_id)],
    ['Preferences digest', cell(profile.preferences_digest)],
    ['Investment-profile digest', cell(profile.investment_profile_digest)],
    ['Price technicals latest', cell(market.price_technicals_latest)],
    ['Macro series latest', cell(market.macro_series_latest)],
    ['Stale price', cell(market.stale_price)],
    ['Stale macro', cell(market.stale_macro)],
    ['Price basket gap', gap.join(', ') || '—'],
    ['Last snapshot', cell(prior.last_snapshot_date)],
    ['Active theses', cell(prior.active_theses_count)],
    ['Attention plan', cell(body.attention_plan_key)],
  ];

  return (
    <div className="space-y-4 text-sm">
      <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Inputs</h3>
      <Table className="border border-hair">
        <TableHeader>
          <TableRow className="border-hair bg-term-bg/80 hover:bg-term-bg/80">
            <TableHead className="text-ink-mute">Slot</TableHead>
            <TableHead className="text-ink-mute">Value</TableHead>
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map(([label, value]) => (
            <TableRow key={label} className="hover:bg-ink/[0.02]">
              <TableCell className="text-ink-mute whitespace-nowrap">{label}</TableCell>
              <TableCell className="text-ink-soft whitespace-normal">{value}</TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  );
}
