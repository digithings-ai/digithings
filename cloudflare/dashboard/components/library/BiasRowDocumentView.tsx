'use client';

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
      <div className="overflow-x-auto border border-hair">
        <table className="w-full text-xs">
          <thead>
            <tr className="text-ink-mute text-left border-b border-hair bg-term-bg/80">
              <th className="px-2 py-2 font-medium">Slot</th>
              <th className="px-2 py-2 font-medium">Value</th>
            </tr>
          </thead>
          <tbody className="divide-y divide-hair">
            {rows.map(([label, value]) => (
              <tr key={label} className="hover:bg-ink/[0.02]">
                <td className="px-2 py-1.5 text-ink-mute whitespace-nowrap">{label}</td>
                <td className="px-2 py-1.5 text-ink-soft">{value}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {notes ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Notes</h3>
          <SafeMarkdown>{notes}</SafeMarkdown>
        </div>
      ) : null}
    </div>
  );
}
