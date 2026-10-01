import { describe, expect, it } from 'vitest';
import type { JobRunView } from '@/lib/settings-api';
import { defaultPipelineSchedule, toggleStage } from '@/lib/settings/pipeline-schedule';
import {
  formatDuration,
  hopsToStrip,
  jobDurationMs,
  jobsToStrip,
  nextScheduledDay,
  notificationStrip,
  planRungId,
  scheduleSummary,
} from '@/lib/settings-runs';
import { planRungs, planSummary, unlocksAt } from '@/lib/settings-plan';

const job = (id: string, status: string, start: string, end: string | null, error: string | null = null): JobRunView => ({
  id,
  job_type: 'overlay_daily',
  status,
  error,
  idempotency_key: id,
  started_at: start,
  finished_at: end,
});

describe('jobsToStrip', () => {
  it('orders oldest to newest, tones by status, summarises', () => {
    const s = jobsToStrip([
      job('c', 'succeeded', '2026-09-03T00:00:00Z', '2026-09-03T00:00:30Z'),
      job('a', 'failed', '2026-09-01T00:00:00Z', '2026-09-01T00:01:05Z', 'no_credentials'),
      job('b', 'skipped', '2026-09-02T00:00:00Z', null),
    ]);
    expect(s.cells.map((c) => c.key)).toEqual(['a', 'b', 'c']);
    expect(s.cells.map((c) => c.tone)).toEqual(['warn', 'off', 'ok']);
    expect(s.cells[0]?.label).toContain('no_credentials');
    expect(s.cells[0]?.label).toContain('1m 5s');
    expect(s.summary).toBe('1 of 3 recent overlay runs succeeded');
  });

  it('keeps only the newest `limit` runs', () => {
    const many = Array.from({ length: 30 }, (_, i) =>
      job(`j${i}`, 'succeeded', new Date(Date.UTC(2026, 8, 1 + (i % 28), i)).toISOString(), null),
    );
    const s = jobsToStrip(many, 20);
    expect(s.cells).toHaveLength(20);
    expect(s.total).toBe(20);
  });

  it('empty input is an honest empty strip', () => {
    const s = jobsToStrip([]);
    expect(s.cells).toEqual([]);
    expect(s.summary).toBe('No overlay runs yet');
  });

  it('duration handles missing or inverted timestamps', () => {
    expect(jobDurationMs({ started_at: null, finished_at: 'x' })).toBeNull();
    expect(jobDurationMs({ started_at: '2026-09-02T00:00:00Z', finished_at: '2026-09-01T00:00:00Z' })).toBeNull();
    expect(formatDuration(450)).toBe('450ms');
    expect(formatDuration(null)).toBe('duration unknown');
  });
});

describe('notificationStrip', () => {
  const now = Date.parse('2026-09-30T12:00:00Z');
  it('builds one cell per day, ok where a send landed', () => {
    const s = notificationStrip(
      [{ sent_date: '2026-09-30' }, { sent_date: '2026-09-30' }, { sent_date: '2026-09-01' }, { sent_date: '2025-01-01' }],
      now,
      30,
    );
    expect(s.cells).toHaveLength(30);
    expect(s.cells.at(-1)).toMatchObject({ key: '2026-09-30', tone: 'ok', label: '2026-09-30: 2 sent' });
    expect(s.cells[0]).toMatchObject({ key: '2026-09-01', tone: 'ok' });
    expect(s.sends).toBe(3);
    expect(s.summary).toBe('3 digest or alert sends in the last 30 days');
  });
});

describe('hopsToStrip', () => {
  it('proven = ok, blocked = warn, bare unproven = off', () => {
    const s = hopsToStrip([
      { key: 'a', label: 'A', proven: true },
      { key: 'b', label: 'B', proven: false, blocker: 'no_credentials' },
      { key: 'c', label: 'C', proven: false },
    ]);
    expect(s.cells.map((c) => c.tone)).toEqual(['ok', 'warn', 'off']);
    expect(s.summary).toBe('1 of 3 remaining hops proven');
    expect(s.cells[1]?.label).toContain('blocked, no_credentials');
  });
});

describe('nextScheduledDay', () => {
  // 2026-09-30 is a Wednesday.
  const wed = Date.parse('2026-09-30T08:00:00Z');
  it('today when enabled', () => {
    expect(nextScheduledDay(defaultPipelineSchedule(), wed)).toMatchObject({ day: 'wednesday', offset: 0 });
  });
  it('skips disabled days and wraps the week', () => {
    let sch = defaultPipelineSchedule();
    for (const d of ['wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const) {
      for (const st of ['research', 'deliberation', 'execution'] as const) {
        sch = toggleStage(sch, d, st);
      }
    }
    expect(nextScheduledDay(sch, wed)).toMatchObject({ day: 'monday', offset: 5 });
  });
  it('null when the whole week is off', () => {
    let sch = defaultPipelineSchedule();
    for (const d of ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const) {
      for (const st of ['research', 'deliberation', 'execution'] as const) sch = toggleStage(sch, d, st);
    }
    expect(nextScheduledDay(sch, wed)).toBeNull();
    expect(scheduleSummary(sch)).toBe('0 of 21 stage slots enabled');
  });
});

describe('plan ladder', () => {
  it('maps tiers to rungs', () => {
    expect(planRungId('free')).toBeNull();
    expect(planRungId('desk')).toBe('desk');
    expect(planRungId('enterprise')).toBe('studio');
  });

  it('marks current and upgrade rungs', () => {
    const r = planRungs('desk', 'monthly');
    expect(r.map((x) => [x.id, x.current, x.upgrade])).toEqual([
      ['brief', false, false],
      ['desk', true, false],
      ['studio', false, true],
    ]);
  });

  it('Observer has every rung as an upgrade', () => {
    expect(planRungs('free', 'annual').every((r) => r.upgrade && !r.current)).toBe(true);
  });

  it('unlock copy derives from entitlements', () => {
    expect(unlocksAt('desk')).toContain('broker_status');
    expect(unlocksAt('desk')).not.toContain('overlay_profile');
    expect(unlocksAt('studio')).toContain('overlay_profile');
  });

  it('summary names the plan and subscription', () => {
    expect(planSummary('desk', 'active')).toBe('Current plan Desk, subscription active');
    expect(planSummary('free')).toBe('Current plan Observer');
  });
});

describe('formatRunStamp', () => {
  it('formats date with UTC time, or date only', async () => {
    const { formatRunStamp } = await import('@/lib/settings-runs');
    expect(formatRunStamp('2026-06-23', '2026-06-23T16:13:04Z')).toBe('Jun 23, 16:13');
    expect(formatRunStamp('2026-06-23', null)).toBe('Jun 23');
    expect(formatRunStamp('2026-06-23', 'garbage')).toBe('Jun 23');
  });
});
