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
  /**
   * The state this record was in before a forced `claim` moved it back to
   * `in_flight` — currently only `"done"`, and only for a forced re-dispatch.
   *
   * A forced re-dispatch that GitHub then declines must NOT end as
   * `dispatch_suppressed`: the earlier run still exists, so demoting the date
   * would throw away the fact it was remediated and let the next plain POST
   * re-dispatch it — the DIG-48 surplus. Remembering where the record came from
   * is what lets `markSuppressed` put it back to `done` instead.
   */
  reclaimed_from?: RemediationState;
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
  /**
   * The claim token this caller now owns: the `claimed_at` `claim` wrote for
   * every date it handed to `toDispatch`.
   *
   * Every settle and release must present it. Without that fence a caller that
   * took 30 minutes to answer could delete or overwrite the claim of a request
   * that has meanwhile aged out and been re-dispatched by somebody else.
   */
  claimedAt: string;
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
   *
   * A forced claim over a `done` date keeps `completed_at` and notes
   * `reclaimed_from: "done"`, so a later decline can restore the record instead
   * of demoting a date that really was remediated.
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
        const reclaimingDone = force && existing?.state === "done";
        const claimable =
          existing === undefined ||
          existing.state === "dispatch_suppressed" ||
          staleClaim === true ||
          reclaimingDone;
        if (!claimable) {
          skipped.push(date);
          continue;
        }
        await txn.put<RemediationRecord>(ledgerKey(date), {
          state: "in_flight",
          claimed_at: now,
          ...(reclaimingDone
            ? { completed_at: existing.completed_at, reclaimed_from: existing.state }
            : {}),
        });
        toDispatch.push(date);
      }
    });

    return { toDispatch, skipped, claimedAt: now };
  }

  /** Mark claimed dates remediated. Only ever called after GitHub accepts. */
  async markDone(dates: string[], now: string, claimedAt: string): Promise<void> {
    await this.settle("markDone", dates, claimedAt, async ({ date, record }) => {
      // `reclaimed_from` is a record of how the claim was taken and is stale the
      // moment the date settles, so it is dropped rather than left behind.
      const { reclaimed_from: _stale, ...rest } = record;
      void _stale;
      await this.state.storage.put<RemediationRecord>(ledgerKey(date), {
        ...rest,
        state: "done",
        completed_at: now,
      });
    });
  }

  /**
   * Record that GitHub declined to start a run for these dates (benign 422).
   *
   * Deliberately not `done`: `markDone` means "a run exists for these dates",
   * and a suppressed dispatch means none does. The date stays dispatchable, so
   * the next POST retries it once the workflow is dispatchable again.
   *
   * Unless this claim *reclaimed* the date from `done`, in which case the run
   * the earlier request started is still standing and the record goes back to
   * `done`. A forced re-dispatch that GitHub declines must not un-remediate a
   * date that was remediated.
   */
  async markSuppressed(
    dates: string[],
    now: string,
    githubStatus: number,
    claimedAt: string,
  ): Promise<void> {
    await this.settle("markSuppressed", dates, claimedAt, async ({ date, record }) => {
      const key = ledgerKey(date);
      if (record.reclaimed_from === "done") {
        // Put back the remediation this forced claim borrowed. `completed_at`
        // is the original acceptance, so it is kept, not stamped with `now`.
        await this.state.storage.put<RemediationRecord>(key, {
          state: "done",
          claimed_at: record.claimed_at,
          completed_at: record.completed_at,
        });
        return;
      }
      await this.state.storage.put<RemediationRecord>(key, {
        ...record,
        state: "dispatch_suppressed",
        suppressed_at: now,
        github_status: githubStatus,
      });
    });
  }

  /**
   * Drop in-flight claims after a failed dispatch so the next request can retry
   * the same date. Settled records — `done` or `dispatch_suppressed` — are left
   * alone; neither is a claim anybody may release.
   *
   * Unless this claim *reclaimed* the date from `done`, in which case the earlier
   * run is still standing and the record goes back to `done` rather than being
   * deleted. Deleting it would leave the date with no ledger entry at all, so the
   * next plain POST would dispatch a date that already has a run — the DIG-48
   * surplus. This is not a hypothetical path: GitHub answers 422 with
   * "The workflow is not valid" when maintenance.yml is disabled, that body is
   * not a benign 422, and the dispatch therefore fails rather than suppressing,
   * which routes here.
   */
  async release(dates: string[], claimedAt: string): Promise<void> {
    await this.settle("release", dates, claimedAt, async ({ date, record }) => {
      if (record.reclaimed_from === "done") {
        await this.state.storage.put<RemediationRecord>(ledgerKey(date), {
          state: "done",
          claimed_at: record.claimed_at,
          completed_at: record.completed_at,
        });
        return;
      }
      if (record.state === "in_flight") {
        await this.state.storage.delete(ledgerKey(date));
      }
    });
  }

  /**
   * Apply a settle/release write to the dates this caller still owns.
   *
   * A date is written only when the stored `claimed_at` is still the token
   * `claim` handed out. That one comparison is the whole fence: it stops a slow
   * request from settling, or worse releasing, a claim that has since aged out
   * and been re-dispatched by somebody else. Without it, request B's release
   * erases request A's live claim, A's markDone then finds no record, and the
   * date is left with no ledger entry although a run exists for it.
   *
   * A skipped write is not an error — it is the fence doing its job — but it is
   * never silent either: a date left with no record is exactly the condition an
   * operator has to be able to see, so each one is logged with its reason.
   */
  private async settle(
    op: "markDone" | "markSuppressed" | "release",
    dates: string[],
    claimedAt: string,
    write: (record: { date: string; record: RemediationRecord }) => Promise<void>,
  ): Promise<void> {
    for (const date of dates) {
      const record = await this.state.storage.get<RemediationRecord>(ledgerKey(date));
      if (!record) {
        this.logSkipped(op, date, "record_missing", undefined);
        continue;
      }
      if (record.claimed_at !== claimedAt) {
        this.logSkipped(op, date, "claim_not_owned", record.claimed_at);
        continue;
      }
      await write({ date, record });
    }
  }

  private logSkipped(
    op: "markDone" | "markSuppressed" | "release",
    date: string,
    reason: "record_missing" | "claim_not_owned",
    storedClaimedAt: string | undefined,
  ): void {
    console.warn(
      JSON.stringify({
        cron: "backfill",
        job: "backfill-ledger",
        op: "ledger_write_skipped",
        settle: op,
        date,
        reason,
        stored_claimed_at: storedClaimedAt ?? null,
      }),
    );
  }
}
