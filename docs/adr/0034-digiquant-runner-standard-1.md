# ADR-0034 — the digiquant runner runs on `standard-1`, and the lock moved with it

**Status:** Accepted (2026-10-19).
**Date:** 2026-10-19
**Author:** Board (local session), on Chris's decision.
**Raised by:** DIG-2904. PR #5903 merged the class change without moving the lock; PR #5924 is this correction.
**Supersedes:** the instance-type clause of the "Chris lock" in `docs/superpowers/plans/2026-09-30-digiquant-house-run-phase3.md` (`:15`, `:28`, `:849`) and `docs/superpowers/plans/2026-10-01-digiquant-phase4-gha-cutover.md` (`:25`, `:671`).
**Amends:** `docs/ops/digiquant-runner.md`, `config/contract/contract.yaml`, `apps/digiquant-runner/container/exec_job_test.py`, and the class comment in the runner image Dockerfile (`infra/docker/Dockerfile.digiquant-runner`).

## Context

`#5903` (merged 2026-10-19T08:23:06Z) right-sized `DigiQuantRunnerContainer` from
`standard-2` (1 vCPU / 6 GiB) to `standard-1` (0.5 vCPU / 4 GiB). It updated
`apps/digiquant-runner/wrangler.toml` and `src/commands.test.ts`, and left five other
artefacts asserting `standard-2`: the image guard in `container/exec_job_test.py`, the ops
doc, the contract entry, both plan locks, and the runner image Dockerfile's class comment. The guard runs in CI under the check
`Test: web apps / lint`, so develop's runner job went red on the next run — the same class
of defect as DIG-4249, a repo-wide red that blocks every PR touching the path.

Two facts change the shape of the decision.

1. **Production was already on `standard-1` before the merge.** `wrangler containers info`
   reported version 10, `vcpu 0.5`, `memory_mib 4096` at 2026-10-18T12:13Z. The code change
   caught up with the deployment; reverting it would have *upsized* production on the next
   deploy, which is why this was put to Chris rather than fixed in the direction the guard
   pointed.
2. **The class was never the cost driver.** DIG-2904's own measured note records that a
   30-minute idle tail was the cost (#5576), with container spend around $20/month. The
   class delta is a fraction of that, and it accrues only while the container is awake.

The guard's authority was the plan lock at `phase3:849`, *"Instance type is **not** open. It
is `standard-2` on `DigiQuantRunnerContainer`."* That is Chris's lock, so only Chris could
move it; he chose to keep the cheaper class on 2026-10-19.

## Decision

Keep `standard-1`. Move every live assertion to it in one change, so the repository, the
contract and production agree. Do not upsize.

## Consequences

- A deploy now changes nothing about the instance class; PR #5924 is production-neutral.
- The guard still stands, on the value the code actually has. It also no longer pins the
  retired pre-#5762 image layout: `image-packages/` is generated at build time and
  gitignored, so the payload assertions now read the generator
  (`scripts/package_r5_image_inputs.py`) instead of the sibling `COPY` lines that no longer
  exist.
- **The hazard the lock was standing in for is untouched.** The plan warns that a price tick
  overlapping the house chain can push the box into OOM *at 6 GiB as well*
  (`phase3:176`, `:833`). Halving the memory halves the margin, and nothing in this change
  buys margin back. Two follow-ups are owed and are tracked on DIG-2904:
  1. make the house chain exclusive against price ticks (`MAX_INFLIGHT` / concurrency
     group) — the plan's own recommended option at `phase3:178`;
  2. make runner memory observable. Today's "peak memory 0, OOM 0" is *no samples*, so a
     near-OOM on a 14,400-second job is currently invisible.
- Acceptance: one measured house run at `standard-1`; revert to `standard-2` if it OOMs.
- Dated plans are not rewritten. Each carries a dated amendment under its lock heading
  pointing here, so the historical reasoning survives alongside the current decision.
