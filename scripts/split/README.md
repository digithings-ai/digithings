# Repo-split path manifest (DIG-3690, parent DIG-3518, goal G07)

`manifest.py` maps every tracked path to exactly one of R0–R7/delete.
`check_boundaries.py` checks Python imports, TypeScript relative imports and
Dockerfile COPYs against the allowed dependency directions.

## Gates

- `python3 scripts/split/manifest.py --check` — fails on any unassigned path.
  This is the hard local-ci gate. Double assignment is impossible by
  construction (first matching rule wins) and is asserted by the suite.
- `python3 scripts/split/check_boundaries.py` — advisory while the P1 decouple
  slices own the residual coupling; `check_boundaries.py --enforce` fails on
  any violation and becomes the gate at the P1 exit check.

There is no `overlaps-known.txt` whitelist: no path may sit in two repos, so
there is nothing to whitelist. It was removed, not replaced.

## Design decisions (Software Architect)

1. Twelve-x desk pages (`apps/dashboard/app/twelve-x/`, `components/twelve-x/`)
   map to R7 even though they live under the `apps/dashboard` tree (R3):
   the R7 scope owns the client desk surface, the R3 scope owns the Brief desk.
2. `apps/dashboard` and the digiquant core pipeline are PRIVATE (R2/R3) per
   Chris's 01:26 calls; the pipeline items (house pipeline,
   `execution/staging_secrets.py`, `vendor_secret_*`, vendor data clients
   gloomberb/luxalgo, `research/docs/RUNBOOK.md`, `config/contract/secrets.yaml`)
   map to R2, the Brief desk tree to R3.
3. `.github/workflows/*` map to delete per DIG-3605 (GHA exit) and never to a
   private repo.
4. Tests and probes of a private subject move with their subject (e.g.
   `tests/dq/test_strategies.py` is R1, `test_mcp_gloomberb_tools.py` is R2).
5. Residual `check_boundaries` violations on the open engine (16 files
   importing the strategy/vendor substrates, plus 3 Dockerfile COPYs) are
   pre-existing coupling owned by slices 1.2 (plugin surface) and 1.7/1.8
   (seeds at boot, Dockerfiles consume packages/images) — not mapping errors.
