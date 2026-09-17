'use client';

import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@digithings/web/ui';
import { SafeMarkdown } from '@/components/SafeMarkdown';

function asRecord(value: unknown): Record<string, unknown> | null {
  if (value && typeof value === 'object' && !Array.isArray(value)) {
    return value as Record<string, unknown>;
  }
  return null;
}

function cell(value: unknown): string {
  if (value == null || value === '') return '—';
  return String(value);
}

export default function BiasRowDocumentView({
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

  const rows: [string, string][] = [
    ['Macro regime', cell(body.macro_regime)],
    ['Equity', cell(body.equity_bias)],
    ['Crypto', cell(body.crypto_bias)],
    ['Bonds', cell(body.bond_bias)],
    ['Commodities', cell(body.commodity_bias)],
    ['Forex', cell(body.forex_bias)],
    ['VIX', cell(body.vix_level)],
    ['Inst flow', cell(body.inst_flow)],
    ['Options', cell(body.options_sentiment)],
    ['CTA', cell(body.cta_direction)],
    ['HF consensus', cell(body.hf_consensus)],
  ];
  const notes = String(body.notes || '').trim();

  return (
    <div className="space-y-4 text-sm">
      <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Bias row</h3>
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
      {notes ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Notes</h3>
          <SafeMarkdown>{notes}</SafeMarkdown>
        </div>
      ) : null}
    </div>
  );
}
