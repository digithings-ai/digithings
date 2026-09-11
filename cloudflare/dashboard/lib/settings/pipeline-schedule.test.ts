import { describe, expect, it } from 'vitest';
import {
  defaultExecutionPolicy,
  defaultPipelineSchedule,
  marketSessionFromTip,
  parseVenuesInput,
  policyFromTip,
  scheduleFromTip,
  toggleStage,
} from './pipeline-schedule';

describe('pipeline-schedule helpers', () => {
  it('defaults enable all stages every weekday', () => {
    const schedule = defaultPipelineSchedule();
    expect(schedule.schema_version).toBe(1);
    for (const day of [
      'monday',
      'tuesday',
      'wednesday',
      'thursday',
      'friday',
      'saturday',
      'sunday',
    ] as const) {
      expect(schedule[day]).toEqual({
        research: true,
        deliberation: true,
        execution: true,
      });
    }
  });

  it('defaults execution policy to venue calendar + defer', () => {
    expect(defaultExecutionPolicy()).toEqual({
      schema_version: 1,
      calendar_mode: 'venue_calendar',
      permitted_venues: [],
      on_closed_session: 'defer',
      respect_early_close: true,
    });
  });

  it('parses tip schedule and toggles a single cell', () => {
    const schedule = scheduleFromTip({
      schema_version: 1,
      saturday: { research: true, deliberation: true, execution: false },
    });
    expect(schedule.saturday.execution).toBe(false);
    expect(schedule.monday.execution).toBe(true);
    const next = toggleStage(schedule, 'saturday', 'execution');
    expect(next.saturday.execution).toBe(true);
    expect(schedule.saturday.execution).toBe(false);
  });

  it('normalizes permitted venues and freezes calendar consts', () => {
    const policy = policyFromTip({
      calendar_mode: 'always_open',
      on_closed_session: 'force',
      permitted_venues: [' nyse ', 'NASDAQ', 'nyse', ''],
      respect_early_close: false,
    });
    expect(policy.calendar_mode).toBe('venue_calendar');
    expect(policy.on_closed_session).toBe('defer');
    expect(policy.permitted_venues).toEqual(['NYSE', 'NASDAQ']);
    expect(policy.respect_early_close).toBe(false);
    expect(parseVenuesInput('nyse, nasdaq nasdaq')).toEqual(['NYSE', 'NASDAQ']);
  });

  it('reads market session when tip exposes it', () => {
    expect(marketSessionFromTip(null)).toBeNull();
    expect(marketSessionFromTip({})).toBeNull();
    const ctx = marketSessionFromTip({
      market_session: {
        venue: 'NYSE',
        is_open: false,
        next_open_at: '2026-09-08T13:30:00Z',
      },
    });
    expect(ctx).toEqual({
      venue: 'NYSE',
      is_open: false,
      session_label: null,
      next_open_at: '2026-09-08T13:30:00Z',
      next_eligible_window: null,
    });
  });
});
