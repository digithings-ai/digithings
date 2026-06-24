import { describe, it, expect } from 'vitest';
import { buildCommandItems } from './command-palette';

const data = {
  portfolio: { strategy: { theses: [{ id: 'MT1', name: 'Small caps' }] } },
  docs: [
    { date: '2026-06-23', title: 'Digest', path: 'digest' },
    { date: '2026-06-23', title: 'IJR analyst', path: 'analyst/IJR' },
    { date: '2026-06-22', title: 'Energy sector', path: 'sector-energy' },
  ],
} as unknown as Parameters<typeof buildCommandItems>[0];

describe('buildCommandItems (F2 palette)', () => {
  it('ships no legacy Why entries and points the read at the Pipeline grammar', () => {
    const items = buildCommandItems(data);
    expect(items.some((i) => i.title.startsWith('Why'))).toBe(false);
    const read = items.find((i) => i.id === 'go-pipeline-read')!;
    expect(read.href).toContain('/pipeline?');
    expect(read.href).toContain('node=digest');
  });
  it('surfaces cross-day docs as Pipeline node deep links, excluding digest', () => {
    const items = buildCommandItems(data);
    const ijr = items.find((i) => i.id === 'doc-2026-06-23-analyst/IJR')!;
    expect(ijr.href).toBe('/pipeline?date=2026-06-23&stage=selection&node=analyst%2FIJR');
    expect(items.some((i) => i.id === 'doc-2026-06-23-digest')).toBe(false);
  });
});
