# Worker-first migration — control plan

Status: **of record once merged**. Supersedes `DIG-2914` / PR #6497 ("keep the
box and clean it") for the Cloudflare runtime.

Owner: Chris. Executed step by step; one step in flight at a time.

## Why this is a programme, not a series of merges

The decision of record said keep the containers. This reverses it. A reversal
carries two extra obligations that an ordinary feature does not:

1. **It needs a baseline before it starts.** Every later claim ("faster",
   "cheaper", "no worse") is meaningless without the number taken while the
   containers still ran.
2. **It deletes things.** A container that is removed cannot be un-removed by
   reverting a commit if a client is mid-session. Deletions go last, and each
   one needs a rollback that is not "revert the merge".

## The case, stated honestly

The money does not carry this. `DIG-2904` measures the whole bill at **$77/mo**;
`DIG-5549` prices emptying the box at **$15–27/mo** against roughly **61k LOC**.
Containers already scale to zero (`sleepAfter` 1 m chat, 5 m stack), so the bill
is wake time, not idle time.

What carries it is **latency and operability**: a Worker wakes in milliseconds; a
container cold start has been measured at **42.9 s**, which is longer than the
shell's own 30 s patience. That is the number to beat, and the baseline file
records the current one.

## Control rules

1. **One step in flight.** No step begins until the previous one has met its
   exit criteria in production, not merely merged.
2. **Entry criteria are measured, not assumed.** Each step names what must be
   true before it starts.
3. **Exit criteria are production measurements.** Merged is not done; a step is
   done when the live surface meets its number.
4. **Rollback is written before the step starts**, and must be executable
   without a new commit (a flag, a config value, a re-dispatch of the previous
   image).
5. **Client surfaces are named per step.** OCC and every DataTap tenant are
   users; a step that cannot be validated on them does not ship.
6. **Deletions are last**, and only after a full week with the replacement
   serving alone.

## Ledger

| # | Step | Entry | Exit (production) | Rollback | Status |
|---|---|---|---|---|---|
| 0 | Baseline + decision of record | — | numbers recorded; `DIG-2914` superseded | n/a | in progress |
| 1 | Per-tenant KV config documents | slice 1 merged | adding a tenant is one KV write, no deploy | re-read previous KV value | not started |
| 2 | Chat container → Worker (`DIG-2912`) | step 1 exit | `/chat` p95 TTFB within the baseline's warm figure; no cold start | dispatch previous image tag | not started |
| 3 | MCP edge completion (`DIG-5629`) | step 2 exit | every tenant's servers callable; scope enforced per server | static key path unchanged | partly done |
| 4 | digikey → Worker (`DIG-5548`) | step 3 exit | token issue/verify with no container in the path | previous container stays warm one release | parked |
| 5 | Runners, dead weight (`DIG-2915`, `DIG-2916`, `DIG-5558`, `#3854`) | step 4 exit | each name gone, nothing references it | re-create from the release ledger | not started |
| 6 | Retire `DigiStackContainer` | step 5 exit + 1 week Worker-only | container deleted, bill reflects it | restore previous image | not started |

## What "in flight" means for this repo

The gate queue is shared. This programme does not jump it, and it does not hold
it either: each step is one branch, one PR, one deploy, and the queue is left
to its own ordering. What it does not accept is a step landing without its
measurement.

## Out of scope

- The UI, chat product behaviour, and tool naming work of the last sessions.
  Those are correctness fixes and stand on their own.
- Moving data storage. KV, R2 and D1 stay as they are.
- Any client migration. No DataTap tenant changes as part of a step.

## Risks

| Risk | Why it is dangerous | Mitigation |
|---|---|---|
| A client is mid-session when a container is deleted | Sessions are not portable | Deletions last; drain window; keep the previous image dispatchable |
| Streaming changes shape when the chat leaves the container | SSE/stream semantics differ | Step 2 measures a full turn, not a health check |
| The Worker's text-binding limit (5.1 kB) bites again | Config grows as tenants are added | Already hit once; split by tenant, tested |
| A step is declared done on "merged" | The original failure mode | Exit criteria are production numbers only |
