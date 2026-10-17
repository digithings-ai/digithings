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

/** Counts and claims carry different prefixes, so a claim never reads as a count. */
const countsKey = (job: string, day: string): string => `counts:${job}:${day}`;
const claimStorageKey = (key: string): string => `claim:${key}`;

/** An unrecorded job or day reads as zeros, never `undefined` and never a throw. */
const emptyDay = (): DayCounts => ({ total: 0, byMinute: {}, byHour: {} });

export class StartCounter {
  /** One instance serves every job. `env` is the Durable Object constructor
   *  contract; this leaf reads no binding, leaf .6 adds `START_COUNTER` to Env. */
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

  /** `true` for the first caller of `key`, `false` for every caller after it
   *  until `releaseKey`. Transactional, so two overlapping callers cannot both
   *  observe an absent key. No TTL: a key is `${job.id}:${scheduledTime}` and a
   *  scheduled time does not recur, so an expiry would re-arm an old duplicate. */
  async claimKey(key: string): Promise<boolean> {
    const storageKey = claimStorageKey(key);
    return this.state.storage.transaction(async (txn) => {
      if (await txn.get(storageKey)) return false;
      await txn.put(storageKey, 1);
      return true;
    });
  }

  /** Drop the claim so `claimKey` can hand this key out again. */
  async releaseKey(key: string): Promise<void> {
    await this.state.storage.delete(claimStorageKey(key));
  }
}