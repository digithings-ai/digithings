## Notifications (email v0)

> Split out of [digiquant/ARCHITECTURE.md](../../ARCHITECTURE.md) (DIG-3399). Prose is unchanged. Relative links were adjusted for this directory.

K5 Cloudflare Email Sending dispatch for daily digest, holding-change, and
execution-alert emails. Module: `digiquant/src/digiquant/notify/`
(`cloudflare_email.py` is the thin stdlib client; `entitlements.py` mirrors T5
`apps/dashboard/lib/entitlements.ts` artifact-class matrix).

**Env:** `CLOUDFLARE_EMAIL_API_TOKEN` (dedicated **Email Sending: Edit** token —
deliberately not the broad deploy token), `CLOUDFLARE_ACCOUNT_ID`, `NOTIFY_FROM`
(required to send); `NOTIFY_UNSUBSCRIBE_BASE` optional (defaults to digiquant.io
settings placeholder). `NOTIFY_FROM` may be a bare address or `Name <addr@domain>`.

**Behavior:** fail-soft for cron/post-run — transport/network errors log a warning and
return; missing notify env logs `NOTIFY_NOT_CONFIGURED` with named keys and skips
(never silent as success in agent probes). Dedupe via `notification_claim` insert-first
PK `(workspace_id, event_key, sent_date)`; suppression is enforced by Cloudflare at
send time (a suppressed recipient is reported on the send response, the client raises
`EmailSuppressedError` and dispatch releases the claim — a DELETE, which is why the
claim has its own mutable table while `notification_log` records only what was sent —
so the send is retried once the address is unsuppressed; there is no pre-send query API);
tier gates on digest sections and event
types (`house_weights_nav` for holding-change, `private_book` for execution alerts);
templates carry unsubscribe link, no broker ids/tokens/keys.

**Loud-fail probe:** `python -m digiquant.notify.dispatch --require-notify` (alias
`--check`) exits **2** with `NOTIFY_NOT_CONFIGURED` listing missing env *names*
when vendor keys are empty. `--dry-run` loads `notification_prefs` and prints
candidate counts (`considered`, `digest_on`, `skipped_prefs_off`,
`skipped_no_email`, `notify_configured`) without sending or claiming
`notification_log` slots — notify absence is `notify_configured=0`, not a
skip of the count. `--workspace-id` filters the plan. Missing store env exits
**2** with `NOTIFY_STORE_NOT_CONFIGURED`. Combined cron probe:
`python scripts/digiquant_cron_check.py` (overlay `--check` + execution sync `--check` +
route `--check` + notify names) exits **2** with `EXECUTION_CRON_CHECK` listing
which probes failed. Route `--check` logs `routing_enabled=true|false` and
never calls `submit_order`. The copy-paste GHA spec also runs
``python -m digiquant.notify.dispatch --dry-run`` (no send, no
``notification_log`` claim).
Staging inventory also covers these names in
`digiquant.execution.staging_secrets`. `scripts/digiquant_staging_e2e.py` runs
Observer Settings hops first (when `DIGIQUANT_STAGING_USER_JWT` or email/password
is set): reads 200, Custom writes `TIER_FORBIDDEN`, then still exits **2** if
vendor secrets are missing (and prints `DIGIQUANT_STAGING_E2E_REMAINING_HOPS` so
the five live hops are named even before secrets land). Observer also POSTs
`/settings/access/redeem-invite` with a short dummy code (`short`, under the
Deno min length) and requires `INVITE_INVALID` or `EMAIL_REQUIRED` — live
settings v32 404s that route. After Observer hops
pass **or fail**, the harness GETs `/settings/profile` (billing snapshot), `/brokers`,
`/jobs`, `/fills`, and `/notifications/log` so remaining hops are named on
exit **3** (live app-urls `/dashboard` vs `/dashboard` plus redeem-invite 404
must not hide product-state blockers). Observer-hop failure still exits **3**.
A hop is proven only from that
product state: `subscription_status=active` **and** `has_stripe_subscription`
**and** `plan_tier` in `{studio, enterprise}` (boolean Stripe id only; house is
seeded `enterprise`/`active` without Stripe ids and must not prove checkout;
Brief or Desk Stripe also must not — overlay stays
`TIER_FORBIDDEN`; ops grants with `subscription_status=none` also do not);
Alpaca paper `active` with `auth_kind=oauth`; `overlay_daily` **succeeded**
(not `running` / `skipped` / `persist_disabled` / `not_entitled`). Persist-on
that finishes `failed` with `error=legacy_book_unique` names
`overlay_legacy_book_unique` (staged cutover 113 not applied) instead of the
generic `overlay_not_succeeded`; a fill
fingerprint with a symbol **and** that OAuth paper connection (`api_key` fills
do not prove the hop); a `digest:`
log key **and** `DIGIQUANT_STAGING_DIGEST_INBOX_CONFIRMED` after an inbox check
**and** `notification_prefs.daily_digest=true` (dispatch skips prefs that are
off; Observer PATCH `/settings/notifications` is not Studio-gated).
Claim-ledger rows are inserted before notify send. Remaining-hop GETs that
are not HTTP 200 exit **3**. Unproven hops log a closed-vocabulary
``blocker=`` code (never Stripe ids) next to ``proven=False`` so the
human-owned gate is named. Exit **0** only when all five remaining hops are
proven. Exit **2** when hops are unproven **and** named vendor secrets are
missing. Checkout URL + unsigned webhook with hops still unproven is **exit 4**.
Phase C (and the Observer checkout hop) POST `tier=studio` — Brief/Desk would
leave overlay `TIER_FORBIDDEN` after Stripe lands.
Recipient for staging digests can be an Agentmail inbox once notify is
configured.

**House pipeline proof:** `python scripts/digiquant_house_pipeline_proof.py` lists
`pipeline-digiquant.yml` runs (landed [#3367](https://github.com/digithings-ai/digithings/pull/3367)
on `develop` `207dd0a68`; fail-close while `main` is `3601f72df`
[#3383](https://github.com/digithings-ai/digithings/pull/3383) `6785c44d4`).
Exit **5** while `origin/main` is still UUID-hotfix `3601f72df` — merge
fail-softs #3343 → #3348 → #3351 → #3354 before the next cron or checkout
`ref: main` still misses those writers (the CLI does not list runs in that
case). On exit 5 it also prints `failsofts=` mergeability from `gh pr view`
(`#3343 OPEN MERGEABLE CLEAN` … `stack ready (do not merge from authoring
agent)`). That line is status only — the authoring agent must not merge those
PRs. `gh run list` `headSha` is the default-branch **trigger** (develop), not
the job checkout, so counting is `created_at` strictly after the later of
#3334 (`2026-08-31T20:39Z`) and current `origin/main` committer time. Exit **0**
only for a **schedule** success after that cutoff. `workflow_dispatch` never
counts. Exit **3** until a counting `schedule` after that cutoff (crons are
`17 9/10/11/12 * * *` — not `0 12 * * *`). A 12:00 UTC run that started
before fail-softs merged does not count. Exit **2** if a counting
schedule fails. The CLI refuses `--dispatch` / `--apply`.

**Entry points:**

| Caller | Function | Digest hour gate |
|--------|----------|------------------|
| Cron `python -m digiquant.notify.dispatch` | `dispatch_notifications(hour_utc=now.hour)` | Yes — matches `digest_hour_utc` |
| House CLI `python -m digiquant.portfolio.chain` (success, not retry) | `dispatch_house_notifications_after_chain` → `force_digest=True` | No — always attempts today's digest; dedupe prevents double-send |
| Probe `… --require-notify` | env presence only (no send) | N/A — exit 2 if incomplete |
| Preview `… --dry-run` | `plan_digest_dispatch` (prefs counts; no send/claim) | N/A — `notify_configured` flag only |
| `run_db_first.py` post-run | `dispatch_notifications(run_date=…, force_digest=True)` | No — always attempts today's digest; dedupe prevents double-send |
| Overlay `run_research_then_portfolio` | none | N/A — nested overlay must not send house mail |
| K4 `run_sync_batch` tail | `dispatch_execution_alerts(run_date=…)` | N/A — execution alerts only |

House GHA (`pipeline-digiquant.yml`) does not yet pass `CLOUDFLARE_EMAIL_API_TOKEN` /
`CLOUDFLARE_ACCOUNT_ID` / `NOTIFY_FROM` into the chain step. Splice
`docs/agent-backlog/execution-tenancy/pipeline-olympus-notify.env.yml` on a
`chore/` or `feat/` branch (`cursor/*` cannot write workflows). Until then the
close-out is fail-soft skip.

Migration 103 (`notification_prefs`, `notification_log`) and 133 (`notification_claim`) + `tests/dq/notify/`.

