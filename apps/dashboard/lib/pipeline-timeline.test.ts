import { describe, expect, it } from 'vitest';
import { buildPipelineTimeline, formatMs } from './pipeline-timeline';
import type { PipelineRunEvent } from './pipeline-trace';

function ev(over: Partial<PipelineRunEvent>): PipelineRunEvent {
  return {
    run_id: 'r1',
    attempt: 1,
    sequence: 0,
    event_kind: 'model_call',
    phase: 'research',
    document_key: null,
    name: null,
    status: 'ok',
    duration_ms: 1000,
    retry_count: 0,
    created_at: null,
    ...over,
  } as PipelineRunEvent;
}

describe('pipeline-timeline', () => {
  it('empty trace still yields six stage rows with honest labels', () => {
    const t = buildPipelineTimeline([]);
    expect(t.rows).toHaveLength(6);
    expect(t.basis).toBe('none');
    expect(t.rows[0].label).toContain('no calls emitted'); // inputs = typed-gap
    expect(t.rows[1].label).toContain('no calls recorded'); // research emits calls
    expect(t.rows.every((r) => r.duration === 0 && r.status === 'mute')).toBe(true);
  });

  it('lays events end to end by sequence when timestamps are missing', () => {
    const t = buildPipelineTimeline([
      ev({ sequence: 1, document_key: 'macro', duration_ms: 2000 }),
      ev({ sequence: 2, document_key: 'digest', phase: 'digest', duration_ms: 3000 }),
    ]);
    expect(t.basis).toBe('sequence');
    expect(t.totalMs).toBe(5000);
    const research = t.rows.find((r) => r.id === 'stage:research')!;
    const synth = t.rows.find((r) => r.id === 'stage:synthesis')!;
    expect(research).toMatchObject({ start: 0, duration: 2000, status: 'ok' });
    expect(synth).toMatchObject({ start: 2000, duration: 3000 });
    expect(t.keyById['key:research:macro']).toBe('macro');
  });

  it('uses created_at as call end when every row has one', () => {
    const t = buildPipelineTimeline([
      ev({ document_key: 'macro', duration_ms: 1000, created_at: '2026-09-30T12:00:01.000Z' }),
      ev({ document_key: 'bonds', duration_ms: 1000, created_at: '2026-09-30T12:00:03.000Z' }),
    ]);
    expect(t.basis).toBe('created_at');
    const macro = t.rows.find((r) => r.id === 'key:research:macro')!;
    const bonds = t.rows.find((r) => r.id === 'key:research:bonds')!;
    expect(macro.start).toBe(0);
    expect(bonds.start).toBe(2000);
  });

  it('flags retries and errors as warn and counts them', () => {
    const t = buildPipelineTimeline([
      ev({ sequence: 1, document_key: 'macro', retry_count: 2 }),
      ev({ sequence: 2, document_key: 'bonds', status: 'error' }),
      ev({ sequence: 3, document_key: 'crypto' }),
    ]);
    expect(t.retries).toBe(2);
    expect(t.errors).toBe(1);
    expect(t.rows.find((r) => r.id === 'stage:research')!.status).toBe('warn');
    expect(t.rows.find((r) => r.id === 'key:research:crypto')!.status).toBe('ok');
  });

  it('caps drill-down rows per stage and counts unmapped events', () => {
    const many = Array.from({ length: 8 }, (_, i) => ev({ sequence: i, document_key: `sector-${i}`, duration_ms: 100 * (i + 1) }));
    const t = buildPipelineTimeline([...many, ev({ phase: 'zzz-unknown' })], 3);
    expect(t.rows.filter((r) => r.id.startsWith('key:research:'))).toHaveLength(3);
    expect(t.unmapped).toBe(1);
  });

  it('formats durations', () => {
    expect(formatMs(0)).toBe('0s');
    expect(formatMs(450)).toBe('450ms');
    expect(formatMs(2500)).toBe('2.5s');
    expect(formatMs(125_000)).toBe('2m 5s');
  });
});
