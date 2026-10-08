# ADR-0031 — nautilus_trader is pinned exactly, and the root `uv.lock` is the only lock

**Status:** Accepted (2026-10-08)
**Date:** 2026-10-08
**Author:** Architect
**Raised by:** DIG-938 (Paperclip), itself raised by the duplicate-realized-PnL defect in DIG-920; gates the analyzer-shape matrix in DIG-937.
**Supersedes:** nothing. **Amends:** the root `AGENTS.md` rule, under *Context & compaction policy*, that *"runtime dependencies are deliberately left unbounded"* (see Consequences). That rule lives in `AGENTS.md`; `docs/agents/CODE_REVIEW_POLICY.md` carries the review-coverage policy and says nothing about dependency bounds.

## Context

DIG-938 reported that `nautilus_trader` "resolves to three different versions in one
repo", and that CI and production both run 1.230.0 while local backtests run 1.228.0.
Re-reading the tree on `origin/develop` at `8accbb296` found **four** states, not three,
and corrected two of the issue's premises. The corrected picture is the reason this ADR
exists, so it is recorded in full:

| where | version | what actually reads it |
|---|---|---|
| `digiquant/.venv` — what runs local backtests | **1.228.0** | the developer |
| root `uv.lock` | **1.230.0** | **all 40 `uv sync` invocations in `.github/workflows/` across 29 workflow files, 35 of which use `--frozen`** |
| `digiquant/uv.lock` | **1.223.0** | **nothing — see below** |
| `digiquant/Dockerfile` → service container | **unpinned; floats to 1.231.0 today** | whatever PyPI serves at build time |
| `Dockerfile.digiquant-runner` (repo root) | **1.230.0, already correct** | `uv sync --frozen --package digiquant --extra nautilus` — installs the engine from the root lock |
| `digiquant/pyproject.toml` declared | `>=1.190,<2` | admits every 1.x minor |

Reproduce the count with `grep -ro "uv sync" .github/workflows/ | wc -l` (40) and
`grep -rn "uv sync" .github/workflows/ | grep -c -- --frozen` (35); the file count is
`grep -rl "uv sync" .github/workflows/ | wc -l` (29).

### Premise 1 corrected: the service image is *not* on 1.230.0 — it is on nothing

CI is genuinely frozen to the root lock. But `digiquant/Dockerfile` copies **only**
`digiquant/pyproject.toml` and runs `uv pip install --system -e ".[nautilus]"`. No
lockfile is copied, and `uv pip install` does not read `uv.lock` at all. The image
therefore resolves the newest 1.x at build time — 1.231.0 as of this ADR, and whatever
is newest on the next rebuild.

Scope that claim precisely, because it is easy to overstate: the pin governs **one**
build surface, `digiquant/Dockerfile`, which `docker-compose.yml` builds. It does **not**
reach the two other digiquant images:

- `apps/digithings-stack-cloudflare/wrangler.toml:115` builds `digiquant/Dockerfile.mcp`,
  which installs `./digiquant[research,mcp]` — **no `nautilus` extra**, so no engine and
  nothing for the pin to fix. The Workers stack was never on a nautilus_trader version.
- `Dockerfile.digiquant-runner` (repo root) already ships the engine correctly:
  `uv sync --frozen --package digiquant --extra nautilus`, i.e. straight from the root
  lock. It is pinned by the lock both before and after this ADR.

And nothing in the repository publishes the service image to GHCR:
`.github/workflows/publish-service-images.yml` was removed in `f54af7052` (the
strict-essentials cut, #4919) and `RELEASES.md` records the removal.

This inverts the risk ordering in the original report. The stale local venv is an
annoyance. The unpinned image is the defect: **the container that a developer
actually runs backtests in is the one build nobody pinned.** (The image is not
published to a registry any more, so "shipped" here means "what
`docker compose up` builds and runs" — see *Scope of the fix* for the publisher.)

### Premise 2 corrected: `digiquant/uv.lock` was never a source of truth

It is referenced **zero** times in any tracked file — no workflow, no Dockerfile, no
compose file, no doc. Last touched by `bdd425414` on 2026-04-18 ("initial baseline"),
never since; the root lock was last touched 2026-10-06.

Stronger than "unreferenced": it was **inert**. It contains **68** packages; the root
lock contains **297**. `digiquant` is a member of the root workspace
(`[tool.uv.workspace] members`). With the module lock present on disk, `uv lock --check`
run from inside `digiquant/` still reports `Resolved 297 packages` and reports
`Found workspace root: …` — uv resolves the **root** lock and never opens the module
lock. It is also the only module in the repository that ships a lock at all.

So the 1.223.0 in the module lock never pinned anything. It was a stale April snapshot
of a pre-workspace digiquant that *read* as a pin, which is why the divergence looked
like an intentional policy decision to everyone who looked at it. The issue's open
question — "is the divergence deliberate?" — answers itself: **it was not deliberate and
it was not even functional.** Nothing in `AGENTS.md`, `ARCHITECTURE.md`, or
`pyproject.toml` claims an intent either way, and uv's behaviour confirms there was
never an intent to honour.

### Why the pin matters at all

`PortfolioAnalyzer.realized_pnls()` changed its Python-visible return type between
1.228.0 and 1.230.0. That is the root cause of the duplicate-realized-PnL defect
(DIG-920) and the thing DIG-937's analyzer-shape matrix must handle. A **minor** bump
inside `>=1.190,<2` moved a return type that our honesty envelope reads. A ranged
pin therefore does not mean "compatible"; it means "silently moves".

## Decision

1. **We ship `nautilus_trader==1.230.0`.** The root lock already resolved it, CI is
   already frozen to it, and DIG-937's measured dedup matrix is measured against its
   semantics. Choosing it changes no package version anywhere — see the lock diff below.
2. **The pin is exact (`==1.230.0`), not ranged.** It is declared in
   `digiquant/pyproject.toml` and carries a comment saying why, pointing here.
3. **The root `uv.lock` is the single authoritative lock for the whole workspace.**
   `digiquant/uv.lock` is deleted. No module ships its own lock; that is the convention,
   and this ADR is the first time it is written down.
4. **The declared range is not the contract.** `digiquant/AGENTS.md` and
   `digiquant/ARCHITECTURE.md` both name 1.230.0 as the shipped build and name the
   root lock as authoritative.

Per the DIG-938 constraint, this is **pin and re-lock only**. No behaviour change to
`realized_pnls` lands here — that belongs to DIG-937 and must stay separable so the
engine bump can be bisected away from the envelope change.

### The lock diff is one line

Re-locking after the pin change resolves **297 packages**, unchanged, and rewrites
exactly one line of the root `uv.lock`:

```diff
-    { name = "nautilus-trader", marker = "extra == 'nautilus'", specifier = ">=1.190,<2" },
+    { name = "nautilus-trader", marker = "extra == 'nautilus'", specifier = "==1.230.0" },
```

The resolved `nautilus-trader` entry stays `1.230.0`. Pinning what the lock already
resolved is provably a no-op for every other dependency — worth stating, because the
alternative (an engine upgrade) would have dragged an unknown transitive set along.

## Consequences

**Positive:**

- One answer to "the build we ship": **1.230.0**, in the lock, in `pyproject.toml`,
  in `digiquant/AGENTS.md`, and in `digiquant/ARCHITECTURE.md`.
- The service container's **engine** is now pinned. Since the Dockerfile copies no
  lockfile, the `==1.230.0` in `pyproject.toml` is the *only* thing that pins
  `nautilus_trader` in it — which is the real fix for the defect Premise 1 found.
  Before this ADR the image tracked PyPI for the engine too.
- The class of defect is named and cannot recur silently: a module-level lock that
  *reads* as a pin is now a written rule with a stated consequence.
- `uv lock --check` passes from the repo root **and** from inside `digiquant/`, so the
  35 `--frozen` lanes stay satisfied and an in-module `uv sync` cannot pick a stale set.
- A second, false source of truth is gone. It was actively misleading: 1.223.0 in
  `digiquant/uv.lock` looked authoritative to every reader and to uv's own resolution
  while pinning nothing.

**Negative / tradeoffs:**

- **This is a deliberate exception to the root `AGENTS.md` rule that "runtime
  dependencies are deliberately left unbounded."** That rule is sound for the
  installable libraries (`digibase`, `digillm`, `digifetch`, `digiskills`, `digivault`),
  where an upper bound propagates to every consumer. `nautilus_trader` is different: it
  is an application dependency of one service, pinned in one place, with a known
  incompatibility (a minor moved a return type we read). The root rule's own escape
  hatch applies — "cap a runtime dep only when there is a *known* incompatibility, and
  say so in a comment next to it" — and that comment is in `digiquant/pyproject.toml`.
  This ADR records the exception so a future reader does not "fix" the pin back to a
  range.
- Bumping nautilus_trader is now a deliberate act with a checklist (below), not an
  incidental resolution. That friction is the point, but it is real.
- **This does not make DIG-937 optional.** The envelope must handle all supported
  shapes regardless of the pin, because we cannot stop upstream from moving within any
  range we widen later, and because the local venv is still on 1.228.0 until someone
  re-syncs it.

### Scope of the fix: what the pin does **not** close

This ADR pins one package. It does **not** make the digiquant image
reproducible, and this ADR must not be read as saying it does.

`digiquant/Dockerfile` runs `uv pip install --system -e ".[nautilus]"` with no
lockfile and no constraints file. The `==1.230.0` is now fixed, but every other
package in the image is resolved from PyPI **at image build time**:
`polars`, `optuna`, `cryptography`, `fastapi`, `uvicorn`, `langgraph`, `httpx`,
`requests`, `statsmodels`, and the whole transitive closure beneath
`nautilus_trader` itself (msgspec, pandas, the Rust-backed wheels). So:

- A rebuild of an **unchanged** commit can produce a **different** image. The
  failure mode is not "the pin broke" but "some transitive dependency moved
  under a tag that did not".
- **No tag is republished, because there is no publisher.**
  `.github/workflows/publish-service-images.yml` — which would have republished `:latest`
  and `:v<pyproject-version>` on every `digiquant/**` push to `main` — was deleted in
  `f54af7052` ("chore(gha): strict-essentials cut + pause CF→disabled traps", #4919) and
  does not exist on `develop` or at this commit. `RELEASES.md` records the removal and
  directs operators to `docker compose build` / `make up`. Nothing else in the tree
  pushes an image either: no workflow, Makefile target, justfile, `scripts/`, `infra/` or
  `.github/actions/` entry, and `renovate.json` only opens PRs.
- The flip side is a **live** problem, not a hypothetical one:
  `infra/self-host/compose.ghcr.yml:34-36` pulls
  `ghcr.io/digithings-ai/digiquant:${DIGI_IMAGE_TAG:-latest}` with
  `build: !reset null` and `pull_policy: always`. That tag nobody publishes, so
  self-host deployments cannot resolve a digiquant image at all. This is separate
  pre-existing rot, not something ADR-0031 introduced, but it is the concrete
  consequence of the publisher's removal and belongs with whoever fixes the self-host
  pull path.
- The pin reaches exactly one build surface. `digiquant/Dockerfile` is built by
  `docker-compose.yml`; that is all. `Dockerfile.mcp` (Workers) installs no nautilus
  extra and `Dockerfile.digiquant-runner` already installs `--frozen` from the root
  lock. Of the surfaces an earlier draft of this ADR named, the exposure is therefore
  one image, not five — and the engine's own version is the only thing this ADR closes.

Closing this needs a lock or a constraints file inside the image build, which is
a change to how images are built rather than a pin change. It is deliberately
**not** in this ADR: the DIG-938 constraint is pin and re-lock only, and folding
an image-build change into the same PR would put two different blast radii in one
review. Tracked as follow-up 4.

### Re-syncing the local venv

Until `uv sync --frozen --package digiquant --extra nautilus` is run in a developer's
checkout, local backtests still run 1.228.0 and CI runs 1.230.0. That is the residual
gap from the original report and it is **not** closed by this ADR — it is closed by
re-syncing, which is a per-checkbook action, not a repo edit. An engineer can still
reproduce a CI-only defect class locally until they do.

### Follow-ups (not in this ADR)

1. **DIG-937** — a CI guard that installs the newest 1.x and runs the analyzer-shape
   matrix, so the next return-type move is caught before it ships rather than after.
   This is the durable guard; the pin is the mitigation.
2. **Re-sync local venvs** to 1.230.0.
3. Consider a repo-level test asserting no module ships a `uv.lock`, so this class of
   stale second-lock cannot reappear silently.
4. **Make the digiquant image reproducible.** The pin fixed the engine inside the
   container; nothing pins the rest of it. The options, in the order I would take
   them:
   - **Copy the root `uv.lock` into the image and install from it** — the one true
     lock, already authoritative for CI, so the container matches CI by
     construction. Needs a `COPY uv.lock` plus switching `uv pip install` to a
     frozen/`--requirement` form; it also means the workspace members installed
     as `-e` paths must stay consistent with the lock.
   - **`uv pip compile` the service's dependency set into a committed
     `requirements.txt`** and install with `-r`. Smaller change, but that file
     becomes a second lock and can drift — which is exactly the failure mode this
     ADR just deleted in `digiquant/uv.lock`. Prefer the first option.
   - **Stop publishing `:v<pyproject-version>` for digiquant, or bump that version
     per release.** Moot as written: nothing publishes it any more (see *Scope of the
     fix*). It matters the moment a publisher returns, because `digiquant`'s static
     `pyproject.toml` version `0.1.0` can never identify a distinct build.
5. **Re-point the self-host pull path at something that exists.** This is the live
   consequence of the publisher's removal and is more urgent than the reproducibility
   work in follow-up 4: `infra/self-host/compose.ghcr.yml:34-36` pulls
   `ghcr.io/digithings-ai/digiquant:${DIGI_IMAGE_TAG:-latest}` with
   `build: !reset null` and `pull_policy: always`, and no workflow publishes that tag.
   Either restore a publisher **that installs from the root lock**, or drop the GHCR
   reference and let compose build locally again. Restoring a publisher is strictly
   better only if it is lock-backed — otherwise it reintroduces a non-reproducible
   `:latest` with an authoritative-looking name on it.
   Items 4 and 5 both belong to Platform/DevOps; they are image-build and packaging
   changes, not dependency decisions.

### Bump checklist (the next time)

1. Change the pin in `digiquant/pyproject.toml`.
2. Run `uv lock` **at the repo root** and read the diff — if it is more than the
   `nautilus-trader` specifier line, stop and reconsider.
3. Verify `uv lock --check` from the root and from inside `digiquant/`.
4. Update the version named in `digiquant/AGENTS.md` and `digiquant/ARCHITECTURE.md`.
5. Run the DIG-937 analyzer-shape matrix against the new build.
6. New ADR (or amend this one) recording what changed and why.

## Links

- Related issues: DIG-938 (this decision), DIG-920 (duplicate realized PnL — root cause),
  DIG-937 (analyzer-shape matrix — the durable guard)
- Repo docs touched: `digiquant/pyproject.toml`, `digiquant/AGENTS.md`,
  `digiquant/ARCHITECTURE.md`, `uv.lock`, deleted `digiquant/uv.lock`
- Evidence for the four-state table: root `uv.lock` (resolved `1.230.0`, `uv lock --check`),
  `digiquant/uv.lock` at `8accbb296` (68 packages, never opened by uv), and
  `digiquant/Dockerfile:33-36` (`COPY digiquant/pyproject.toml ./` then
  `uv pip install --system -e ".[nautilus]"`, no lockfile).