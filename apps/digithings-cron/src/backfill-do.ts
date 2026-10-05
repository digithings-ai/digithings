/**
 * BackfillLedger — per-date remediation state for POST /backfill.
 *
 * ## Why a Durable Object and not KV
 *
 * Idempotence per date is only worth anything if two requests carrying the same
 * date cannot both decide it is unremediated. KV has no atomic
 * read-modify-write, so two overlapping kicks could each read "absent" and each
 * dispatch — which is exactly the double-backfill that produced the surplus in
 * the first place. A Durable Object is single-threaded per id, so the
 * read-decide-write below is one atomic step and one caller wins.
 *
 * ## Storage keys
 *
 * `backfill:<date>`. The `backfill:` prefix is disjoint from the `counts:` and
 * `claim:` keys StartCounter owns, so the two objects can never collide on a key
 * even if they are ever pointed at the same storage.
 */

import type { Env } from "./env";

/**
 * Three states, not two, because "GitHub accepted the run" and "GitHub declined
 * to start one" are different facts and only the first one is remediation:
 *
 * - `in_flight` — claimed by a request that has not settled yet.
 * - `done` — GitHub answered 204/200, so a run was started for these dates.
 * - `dispatch_suppressed` — GitHub answered a benign 422 (workflow disabled,
 *   already queued, already running). Nothing ran, so this is NOT `done`, and it
 *   must stay dispatchable: recording it as `done` would answer every later
 *   retry with "already remediated" and the date would never be backfilled.
 */
export type RemediationState = "in_flight" | "done" | "dispatch_suppressed";

export interface RemediationRecord {
  state: RemediationState;
  claimed_at: string;
  completed_at?: string;
  suppressed_at?: string;
  github_status?: number;
}

/**
 * How long an `in_flight` claim may stand before `claim` treats it as abandoned.
 *
 * A dispatch settles in seconds. `postGithub`'s own retry budget (3 attempts,
 * `Retry-After` honoured up to 30s each) can hold a claim a little over a
 * minute. Half an hour is far above any honest in-flight window and far below
 * "the operator never retries" — which is where an unbounded claim ends up:
 * a request killed between `claim` and `markDone`/`release` (isolate eviction,
 * client abort) would otherwise lock the date out permanently while every later
 * POST claims it is already remediated.
 */
export const IN_FLIGHT_TTL_MS = 30 * 60 * 1000;

export type LedgerSplit = {
  /** Dates this caller owns and must dispatch. */
  toDispatch: string[];
  /** Dates already claimed or already remediated — do not dispatch. */
  skipped: string[];
};

const KEY_PREFIX = "backfill:";

export function ledgerKey(date: string): string {
  return `${KEY_PREFIX}${date}`;
}

/**
 * A claim older than `IN_FLIGHT_TTL_MS` belongs to a request that is no longer
 * running. An unparseable `claimed_at` is not evidence of a live request either,
 * so it is treated as abandoned rather than as a permanent lockout.
 */
export function isStaleClaim(record: RemediationRecord, nowMs: number): boolean {
  const claimedMs = Date.parse(record.claimed_at);
  const age = Number.isNaN(claimedMs) ? Number.POSITIVE_INFINITY : nowMs - claimedMs;
  return age > IN_FLIGHT_TTL_MS;
}

export class BackfillLedger {
  constructor(
    private readonly state: DurableObjectState,
    env: Env,
  ) {
    void env;
  }

  /** Current state per date. Absent dates read as "unknown" (never remediated). */
  async status(dates: string[]): Promise<Record<string, RemediationState | "unknown">> {
    const out: Record<string, RemediationState | "unknown"> = {};
    for (const date of dates) {
      const record = await this.state.storage.get<RemediationRecord>(ledgerKey(date));
      out[date] = record?.state ?? "unknown";
    }
    return out;
  }

  /**
   * Partition `dates` into the ones this caller may dispatch and the ones it
   * must skip, marking the former in flight in the same transaction.
   *
   * A date is claimable when it has never been claimed, when its previous
   * dispatch was suppressed, when its claim has aged out (`isStaleClaim`), or
   * when `force` is set and it is already `done`. `force` is the explicit,
   * audited override for a date GitHub already accepted: re-running a date that
   * succeeded is the remediation path, not something a plain retry may do.
   */
  async claim(dates: string[], now: string, force: boolean): Promise<LedgerSplit> {
    const toDispatch: string[] = [];
    const skipped: string[] = [];
    const nowMs = Date.parse(now);

    await this.state.storage.transaction(async (txn) => {
      for (const date of dates) {
        const existing = await txn.get<RemediationRecord>(ledgerKey(date));
        const staleClaim = existing?.state === "in_flight" && isStaleClaim(existing, nowMs);
        // A suppressed dispatch started no run, so this date is still owed a
        // backfill and stays claimable for any later request. That is what turns
        // "workflow was disabled" into a retry instead of a silent no-op.
        const claimable =
          existing === undefined ||
          existing.state === "dispatch_suppressed" ||
          staleClaim === true ||
          (force && existing.state === "done");
        if (!claimable) {
          skipped.push(date);
          continue;
        }
        await txn.put<RemediationRecord>(ledgerKey(date), {
          state: "in_flight",
          claimed_at: now,
        });
        toDispatch.push(date);
      }
    });

    return { toDispatch, skipped };
  }

  /** Mark claimed dates remediated. Only ever called after GitHub accepts. */
  async markDone(dates: string[], now: string): Promise<void> {
    for (const date of dates) {
      const key = ledgerKey(date);
      const record = await this.state.storage.get<RemediationRecord>(key);
      if (!record) continue;
      await this.state.storage.put<RemediationRecord>(key, {
        ...record,
        state: "done",
        completed_at: now,
      });
    }
  }

  /**
   * Record that GitHub declined to start a run for these dates (benign 422).
   *
   * Deliberately not `done`: `markDone` means "a run exists for these dates",
   * and a suppressed dispatch means none does. The date stays dispatchable, so
   * the next POST retries it once the workflow is dispatchable again.
   */
  async markSuppressed(dates: string[], now: string, githubStatus: number): Promise<void> {
    for (const date of dates) {
      const key = ledgerKey(date);
      const record = await this.state.storage.get<RemediationRecord>(key);
      if (!record) continue;
      await this.state.storage.put<RemediationRecord>(key, {
        ...record,
        state: "dispatch_suppressed",
        suppressed_at: now,
        github_status: githubStatus,
      });
    }
  }

  /**
   * Drop in-flight claims after a failed dispatch so the next request can retry
   * the same date. Settled records — `done` or `dispatch_suppressed` — are left
   * alone; neither is a claim anybody may release.
   */
  async release(dates: string[]): Promise<void> {
    for (const date of dates) {
      const key = ledgerKey(date);
      const record = await this.state.storage.get<RemediationRecord>(key);
      if (record?.state !== "in_flight") continue;
      await this.state.storage.delete(key);
    }
  }
}
