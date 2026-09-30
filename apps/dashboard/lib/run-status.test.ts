import { describe, expect, it } from 'vitest';
import { classifyRunStatus, describeRunStatus, RUN_STATUS_SEVERITY, runStatusView } from './run-status';

describe('run-status', () => {
  it('complete with no carry, failure or retry', () => {
    expect(classifyRunStatus({ status: 'completed' })).toBe('complete');
    expect(classifyRunStatus({ status: 'ok', outcome: 'ok', attempts: 1 })).toBe('complete');
  });

  it('carry alone is complete-with-carry and reads accent, never warn', () => {
    const v = describeRunStatus({ status: 'completed', segmentsCarried: 3, segmentsFailed: 0 });
    expect(v.kind).toBe('complete-with-carry');
    expect(v.tone).toBe('accent');
    // The engine tags carry runs as "degraded": still just carry.
    const engine = describeRunStatus({ status: 'degraded', segmentsCarried: 4, outcome: 'degraded' });
    expect(engine.kind).toBe('complete-with-carry');
    expect(engine.tone).toBe('accent');
  });

  it('degraded without any carry evidence is attention (warn)', () => {
    const v = describeRunStatus({ status: 'degraded', segmentsCarried: 0, outcome: 'degraded' });
    expect(v.kind).toBe('attention');
    expect(v.tone).toBe('warn');
  });

  it('retried or recovered episodes are attention, even when carry is present', () => {
    expect(classifyRunStatus({ status: 'ok', outcome: 'recovered' })).toBe('attention');
    expect(classifyRunStatus({ status: 'ok', attempts: 2, segmentsCarried: 2 })).toBe('attention');
  });

  it('failed segments or failed status win over everything, with warn (not down)', () => {
    expect(classifyRunStatus({ status: 'ok', segmentsFailed: 1, segmentsCarried: 2 })).toBe('failed');
    expect(classifyRunStatus({ status: 'error' })).toBe('failed');
    expect(classifyRunStatus({ outcome: 'failed', attempts: 3 })).toBe('failed');
    expect(describeRunStatus({ status: 'failed' }).tone).toBe('warn');
  });

  it('unrecognised status is neutral and keeps its text', () => {
    const v = describeRunStatus({ status: 'queued' });
    expect(v.kind).toBe('unknown');
    expect(v.tone).toBe('mute');
    expect(v.headline).toBe('Pipeline queued');
  });

  it('orders severity failed > attention > carry > complete', () => {
    const s = RUN_STATUS_SEVERITY;
    expect(s.failed).toBeGreaterThan(s.attention);
    expect(s.attention).toBeGreaterThan(s['complete-with-carry']);
    expect(s['complete-with-carry']).toBeGreaterThan(s.complete);
  });

  it('no-telemetry is mute and no-run is idle', () => {
    expect(runStatusView('no-telemetry').tone).toBe('mute');
    expect(runStatusView('no-run').tone).toBe('idle');
  });
});
