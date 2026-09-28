/**
 * Workspace PipelineSchedule / ExecutionPolicy helpers for the Settings Pipeline tab.
 * Mirrors digiquant.profiles.pipeline_schedule + execution_policy defaults.
 */

export const WEEKDAYS = [
  'monday',
  'tuesday',
  'wednesday',
  'thursday',
  'friday',
  'saturday',
  'sunday',
] as const;

export type WeekdayName = (typeof WEEKDAYS)[number];

export const STAGES = ['research', 'deliberation', 'execution'] as const;

export type StageName = (typeof STAGES)[number];

export type DayStageFlags = {
  research: boolean;
  deliberation: boolean;
  execution: boolean;
};

export type PipelineScheduleState = {
  schema_version: number;
} & Record<WeekdayName, DayStageFlags>;

export type ExecutionPolicyState = {
  schema_version: number;
  calendar_mode: 'venue_calendar';
  permitted_venues: string[];
  on_closed_session: 'defer';
  respect_early_close: boolean;
};

/** Optional market-session context when a future tip/API exposes it. */
export type MarketSessionContext = {
  venue?: string | null;
  is_open?: boolean | null;
  session_label?: string | null;
  next_open_at?: string | null;
  next_eligible_window?: string | null;
};

export const WEEKDAY_LABELS: Record<WeekdayName, string> = {
  monday: 'Mon',
  tuesday: 'Tue',
  wednesday: 'Wed',
  thursday: 'Thu',
  friday: 'Fri',
  saturday: 'Sat',
  sunday: 'Sun',
};

export const STAGE_LABELS: Record<StageName, string> = {
  research: 'Research',
  deliberation: 'Deliberation',
  execution: 'Execution',
};

export function defaultDayFlags(): DayStageFlags {
  return { research: true, deliberation: true, execution: true };
}

/** Contract defaults: all stages enabled every weekday. */
export function defaultPipelineSchedule(): PipelineScheduleState {
  const day = defaultDayFlags();
  return {
    schema_version: 1,
    monday: { ...day },
    tuesday: { ...day },
    wednesday: { ...day },
    thursday: { ...day },
    friday: { ...day },
    saturday: { ...day },
    sunday: { ...day },
  };
}

/** Contract defaults: venue calendar + defer + respect early close. */
export function defaultExecutionPolicy(): ExecutionPolicyState {
  return {
    schema_version: 1,
    calendar_mode: 'venue_calendar',
    permitted_venues: [],
    on_closed_session: 'defer',
    respect_early_close: true,
  };
}

function asBool(value: unknown, fallback: boolean): boolean {
  return typeof value === 'boolean' ? value : fallback;
}

function parseDay(raw: unknown): DayStageFlags {
  const defaults = defaultDayFlags();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return defaults;
  const obj = raw as Record<string, unknown>;
  return {
    research: asBool(obj.research, defaults.research),
    deliberation: asBool(obj.deliberation, defaults.deliberation),
    execution: asBool(obj.execution, defaults.execution),
  };
}

export function scheduleFromTip(raw: unknown): PipelineScheduleState {
  const base = defaultPipelineSchedule();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base;
  const obj = raw as Record<string, unknown>;
  const next = { ...base };
  if (typeof obj.schema_version === 'number' && Number.isInteger(obj.schema_version)) {
    next.schema_version = Math.max(1, obj.schema_version);
  }
  for (const day of WEEKDAYS) {
    next[day] = parseDay(obj[day]);
  }
  return next;
}

export function policyFromTip(raw: unknown): ExecutionPolicyState {
  const base = defaultExecutionPolicy();
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base;
  const obj = raw as Record<string, unknown>;
  const venues = Array.isArray(obj.permitted_venues)
    ? obj.permitted_venues
        .filter((v): v is string => typeof v === 'string')
        .map((v) => v.trim().toUpperCase())
        .filter(Boolean)
    : [];
  const unique: string[] = [];
  for (const v of venues) {
    if (!unique.includes(v)) unique.push(v);
  }
  return {
    schema_version:
      typeof obj.schema_version === 'number' && Number.isInteger(obj.schema_version)
        ? Math.max(1, obj.schema_version)
        : base.schema_version,
    calendar_mode: 'venue_calendar',
    permitted_venues: unique,
    on_closed_session: 'defer',
    respect_early_close: asBool(obj.respect_early_close, base.respect_early_close),
  };
}

/**
 * Read optional market-session fields from a profile tip (or nested policy)
 * when the API already exposes them; otherwise return null.
 */
export function marketSessionFromTip(tip: Record<string, unknown> | null | undefined): MarketSessionContext | null {
  if (!tip) return null;
  const candidates: unknown[] = [
    tip.market_session,
    tip.execution_session,
    tip.execution_market_context,
  ];
  const policy = tip.execution_policy;
  if (policy && typeof policy === 'object' && !Array.isArray(policy)) {
    const p = policy as Record<string, unknown>;
    candidates.push(p.market_session, p.session_context);
  }
  for (const raw of candidates) {
    if (!raw || typeof raw !== 'object' || Array.isArray(raw)) continue;
    const obj = raw as Record<string, unknown>;
    const ctx: MarketSessionContext = {
      venue: typeof obj.venue === 'string' ? obj.venue : null,
      is_open: typeof obj.is_open === 'boolean' ? obj.is_open : null,
      session_label: typeof obj.session_label === 'string' ? obj.session_label : null,
      next_open_at: typeof obj.next_open_at === 'string' ? obj.next_open_at : null,
      next_eligible_window:
        typeof obj.next_eligible_window === 'string' ? obj.next_eligible_window : null,
    };
    if (
      ctx.venue ||
      ctx.is_open !== null ||
      ctx.session_label ||
      ctx.next_open_at ||
      ctx.next_eligible_window
    ) {
      return ctx;
    }
  }
  return null;
}

export function toggleStage(
  schedule: PipelineScheduleState,
  day: WeekdayName,
  stage: StageName,
): PipelineScheduleState {
  return {
    ...schedule,
    [day]: {
      ...schedule[day],
      [stage]: !schedule[day][stage],
    },
  };
}

export function parseVenuesInput(raw: string): string[] {
  const unique: string[] = [];
  for (const part of raw.split(/[\s,]+/)) {
    const v = part.trim().toUpperCase();
    if (!v || unique.includes(v)) continue;
    unique.push(v);
  }
  return unique;
}
