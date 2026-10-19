import type { Env } from "./env";

/**
 * Starts a cron owes on one UTC day, per job. Durable Object rather than KV
 * because KV has no atomic read-modify-write, and JavaScript interleaves at
 * every await: a get-then-put drops one of two concurrent starts, or hands one
 * claim key to two callers. Both are the bug this epic exists to close.
 */

/** One job's starts on one UTC day, as stored. */
interface DayCounts {
  total: number;
  byMinute: Record<string, number>;
  byHour: Record<string, number>;
}

/** One job's starts on one UTC day, as read. */
export interface StartCounts extends DayCounts {
  /** Job id these counts belong to. */
  job: string;
  /** UTC day `YYYY-MM-DD` these counts belong to. */
  day: string;
}

/** One job's claimed cron slots on one UTC day, as stored. */
type DaySlots = Record<string, 1>;

/** Counts and claims carry different prefixes, so a claim never reads as a count. */
const countsKey = (job: string, day: string): string => `counts:${job}:${day}`;
const slotsKey = (key: string, day: string): string => `slots:${key}:${day}`;
/** The last day `claimSlot` wrote for a key, so the day before it can be dropped. */
const slotDayKey = (key: string): string => `slotDay:${key}`;

/** An unrecorded job or day reads as zeros, never `undefined` and never a throw. */
const emptyDay = (): DayCounts => ({ total: 0, byMinute: {}, byHour: {} });

export class StartCounter {
  /** One instance serves every job. `env` is the Durable Object constructor
   *  contract; this leaf reads no binding. `START_COUNTER` is bound in
   *  wrangler.toml (migration v2) and used by scheduled() in index.ts. */
  constructor(private readonly state: DurableObjectState, env: Env) {
    void env;
  }

  /** Add one start. Increments, so two starts in the same minute stay two. */
  async record(job: string, day: string, minute: string, hour: string): Promise<void> {
    const key = countsKey(job, day);
    await this.state.storage.transaction(async (txn) => {
      const counts = (await txn.get<DayCounts>(key)) ?? emptyDay();
      counts.total += 1;
      counts.byMinute[minute] = (counts.byMinute[minute] ?? 0) + 1;
      counts.byHour[hour] = (counts.byHour[hour] ?? 0) + 1;
      await txn.put(key, counts);
    });
  }

  /** What this job started on this day. Persisted on every record, so an
   *  eviction cannot lose a day. */
  async get(job: string, day: string): Promise<StartCounts> {
    const stored = (await this.state.storage.get<DayCounts>(countsKey(job, day))) ?? emptyDay();
    return { job, day, ...stored };
  }

  /**
   * `true` for the first caller of `key` on `slot`, `false` for every caller
   * after it until `releaseSlot`.
   *
   * `slot` is `YYYY-MM-DDTHH:MM`, the cron minute the job is owed in. A minute
   * does not recur, so a claim never has to expire to avoid re-arming a
   * duplicate — but the rows would accumulate forever (an every-minute clock
   * writes one a minute), so the same transaction that claims today deletes the
   * last other day this key wrote. One day of slots per key is all any caller
   * can still need: a tick is delivered within seconds, never days.
   *
   * Transactional, so two overlapping callers cannot both observe an absent
   * slot.
   */
  async claimSlot(key: string, slot: string): Promise<boolean> {
    const day = slot.slice(0, 10);
    const dayKey = slotsKey(key, day);
    const markerKey = slotDayKey(key);
    return this.state.storage.transaction(async (txn) => {
      const slots = (await txn.get<DaySlots>(dayKey)) ?? {};
      if (slots[slot]) return false;
      slots[slot] = 1;
      await txn.put(dayKey, slots);
      const previous = await txn.get<string>(markerKey);
      // Only ever move forward. A tick scheduled at 23:59 can be delivered just
      // after midnight, so `day` is not always the newer date; dropping the
      // newer day in that case would forget today's claims.
      if (previous === undefined || previous < day) {
        if (previous) await txn.delete(slotsKey(key, previous));
        await txn.put(markerKey, day);
      }
      return true;
    });
  }

  /** Drop the slot so `claimSlot` can hand it out again after a failed dispatch. */
  async releaseSlot(key: string, slot: string): Promise<void> {
    const dayKey = slotsKey(key, slot.slice(0, 10));
    await this.state.storage.transaction(async (txn) => {
      const slots = await txn.get<DaySlots>(dayKey);
      if (!slots?.[slot]) return;
      delete slots[slot];
      if (Object.keys(slots).length === 0) await txn.delete(dayKey);
      else await txn.put(dayKey, slots);
    });
  }
}