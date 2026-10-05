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

export type RemediationState = "in_flight" | "done";

export interface RemediationRecord {
  state: RemediationState;
  claimed_at: string;
  completed_at?: string;
}

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
   * `force` re-dispatches dates already marked `done` — the deliberate
   * remediation path. It never steals a date that is currently `in_flight`,
   * because that claim belongs to a request that has not learned its dispatch
   * failed yet; taking it would let two runs write the same date.
   */
  async claim(dates: string[], now: string, force: boolean): Promise<LedgerSplit> {
    const toDispatch: string[] = [];
    const skipped: string[] = [];

    await this.state.storage.transaction(async (txn) => {
      for (const date of dates) {
        const existing = await txn.get<RemediationRecord>(ledgerKey(date));
        const claimable =
          existing === undefined || (force && existing.state === "done");
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
   * Drop in-flight claims after a failed dispatch so the next request can retry
   * the same date. Records already marked `done` are left alone.
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
