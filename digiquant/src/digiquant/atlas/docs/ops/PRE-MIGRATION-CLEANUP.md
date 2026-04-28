# Pre-migration cleanup (lean repo before DigiThings)

**Goal:** Reduce noise in **digiquant-atlas** so what you copy into **DigiThings** is **intentional**—runtime + operator tooling + docs—without deleting anything required for today’s pipeline.

**After cleanup:** follow [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md) (Wave 1 → Wave 2 DigiGraph → Wave 3 tenancy).

---

**P0 status:** Migrations are treated as **append-only** for applied Supabase projects; see [docs/ops/README.md](README.md) one-liner and [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md).

---

## 1. What *not* to do (important)

### Supabase SQL migrations (`supabase/migrations/*.sql`)

- **Do not delete** migration files that have already been applied to **production** (or any long-lived Supabase project). Supabase/Postgres migration history assumes **append-only** ordered files; removing `015_*.sql` because it “looks old” will break fresh clones and `supabase db push` story.
- **“SQL we no longer need”** usually means *redundant documentation* or *one-off SQL you ran in the editor*, **not** files in `supabase/migrations/`.
- **Squashing** migrations is a **controlled** process (new project or downtime + rebuild)—only if you explicitly plan a **greenfield** DB. Treat as out of scope for a “lean copy” unless you’re doing that project.

### Canonical pipeline

- Do not remove scripts referenced from [RUNBOOK.md](../../RUNBOOK.md), [docs/ops/SCRIPTS.md](SCRIPTS.md), [`.github/workflows/`](../../.github/workflows/), or [`tests/`](../../tests/) without replacing call sites.

---

## 2. Safe, recommended hygiene (no schema risk)

| Action | Detail |
|--------|--------|
| **Local scratch** | The entire **`data/`** tree is **gitignored** (not tracked). Scripts recreate it when needed (price CSV cache, optional scratch). **Do not** commit anything under `data/`. |
| **Outputs** | `outputs/` is deprecated and gitignored—ensure nothing in CI depends on it. |
| **Odd paths** | Remove stray folders under `data/agent-cache/` from bad CLI invocations (e.g. `--help` interpreted as a path). |

---

## 3. Script inventory (audit, then quarantine or delete)

There are **~57** Python files under [`scripts/`](../../scripts/). [SCRIPTS.md](SCRIPTS.md) already groups them:

| Bucket | Cleanup stance |
|--------|----------------|
| **DB-first / daily** (`run_db_first`, `publish_document`, `validate_db_first`, `materialize_snapshot`, `preload-history`, `refresh_performance_metrics`, …) | **Keep** — core. |
| **CI / GitHub** (called from workflows) | **Keep** — grep [`.github/workflows`](../../.github/workflows) before removing. |
| **Migration / legacy** (SCRIPTS.md § “Migration / legacy”) | **Keep in repo** until you confirm no operator uses them; optional move to `scripts/legacy/` + README. |
| **One-off repairs** (`repair_*.py`, `fix_*.py`, incident-specific `backfill_*`) | **Delete** from the repo once the DB is healed and you no longer need the script — do not keep shadow copies under alternate folders. |
| **Large utilities** (e.g. `normalize_supabase_documents.py`) | **Keep** as ops tooling; not frontend bundle. |

**Suggested audit commands** (run from repo root):

```bash
# Scripts not referenced in markdown (heuristic — review manually)
rg -l 'scripts/' --glob '*.md' --glob '*.yml' . > /tmp/script-refs.txt
ls scripts/*.py | while read f; do bn=$(basename "$f"); rg -q "$bn" . || echo "UNREFERENCED? $f"; done
```

Treat “unreferenced” as **candidate only**—Python may import another script dynamically.

---

## 4. Skills inventory (`skills/**/SKILL.md`)

There are **~49** skill folders. The **orchestrator** ([`skills/orchestrator/SKILL.md`](../../skills/orchestrator/SKILL.md)) references a **large subset** (alt-data, macro, sectors, portfolio-manager, deliberation, etc.). **Research-only** and **Track B** tasks also pull in **research-daily**, **weekly-baseline**, **market-thesis-exploration**, **thesis-vehicle-map**, **github-workflow**, **research-library**, **deep-dive**, **monthly-synthesis**, etc.

| Stance | Detail |
|--------|--------|
| **Do not delete** a skill until you grep for `skills/<name>` and `cowork/tasks`, and confirm DigiGraph will not invoke it in Wave 2. |
| **Consolidation** (optional): merge tiny sector skills later—**not** required pre-migration. |
| **`.claude/skills/`** | Editor/plugin copies—dedupe vs `skills/` when convenient; **canonical** agent instructions stay under **`skills/`**. |

---

## 5. Migration baseline (no in-repo archives)

For a clean export to DigiThings, **`archive/`**, **`docs/archive/`**, and incident-only repair trees are **not** kept in this repository. **Architecture** is documented in [`docs/agentic/ARCHITECTURE.md`](../agentic/ARCHITECTURE.md) (root [`docs/ARCHITECTURE-REVIEW.md`](../../docs/ARCHITECTURE-REVIEW.md) redirects there). Operator truth: [`RUNBOOK.md`](../../RUNBOOK.md).

---

## 6. Phased cleanup checklist (execute in order)

- [x] **P0 — Confirm DB migration policy** — no deletion of applied `supabase/migrations/*.sql` without a migration-squash project. (See [docs/ops/README.md](README.md) + [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md).)
- [x] **P1 — Local hygiene** — purge ignored `data/*` on dev machines; document “empty `data/` on clone” in README or SETUP.
- [x] **P2 — Workflow grep** — list every script invoked from `.github/workflows/*.yml`; mark as **protected** ([PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md)).
- [x] **P3 — Repair scripts** — Apr 2026 one-shots **removed** from the repo; [`scripts/repair_supabase_portfolio_data.py`](../../scripts/repair_supabase_portfolio_data.py) remains in smoke-test.
- [x] **P4 — Skills** — see [SKILLS-AUDIT.md](SKILLS-AUDIT.md) (no skill folder deletions).
- [x] **P5 — Optional folder moves** — `scripts/legacy/` **deferred** (see [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md) § Optional layout); **no** `archive/` trees retained in-repo.
- [x] **P6 — README / SETUP** — pointers in [README.md](../../README.md), [SETUP_GUIDE.md](../../SETUP_GUIDE.md); migration next: [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md).
- [x] **P7 — Systematic cleanup pass** — local `data/agent-cache/` cleared; [REPOSITORY-INVENTORY.md](REPOSITORY-INVENTORY.md) § 5 core items checked; `./scripts/smoke-test.sh` all green (45 checks); `git ls-files` has no `.DS_Store`; [README.md](../../README.md) / [SETUP_GUIDE.md](../../SETUP_GUIDE.md) aligned with tracked `data/README.md`.

---

## 7. Definition of done (pre-migration)

- **Single story** for “what ships to DigiThings”: `frontend/`, `supabase/`, `scripts/`, `skills/`, `templates/`, `config/` (examples + non-secret), `cowork/`, `docs/` (trimmed), CI workflows — **no** parallel `archive/` documentation trees.
- **No reliance** on committed scratch under `data/`.
- **Protected list** maintained at [PROTECTED-SCRIPTS.md](PROTECTED-SCRIPTS.md); **skills audit** at [SKILLS-AUDIT.md](SKILLS-AUDIT.md).
- **Migration roadmap** filed as [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md) and ready to open as PR context in DigiThings.
- **Full repository accounting:** every top-level folder and policy for gitignored paths — [REPOSITORY-INVENTORY.md](REPOSITORY-INVENTORY.md). Re-run `git ls-files | wc -l` after major moves; update § 1 counts in that file.

---

## 8. Perfect cleanup (optional last pass)

Use [REPOSITORY-INVENTORY.md](REPOSITORY-INVENTORY.md) § 5 as a **folder-by-folder** verification before Wave 1. It does not replace the phased checklist above — it **proves** nothing unexpected is tracked and secrets stay ignored.

---

## 9. Verification record (repeat before Wave 1 export)

Run from repo root:

```bash
git ls-files | wc -l                    # expect ~388; update REPOSITORY-INVENTORY §1 if changed
git ls-files | grep -i ds_store || true # expect empty
./scripts/smoke-test.sh                 # expect 45 passed
```

Ensure **only** `data/README.md` is intended under `data/` in git (`git ls-files data/`). Local `data/agent-cache/` may reappear after runs — **delete** before export if you want a bare tree (`rm -rf data/agent-cache`).

**Last full pass:** 2026-04-15 — P7 checklist items above satisfied; optional items in [REPOSITORY-INVENTORY.md](REPOSITORY-INVENTORY.md) § 5 (editor skill dedupe, `docs/research/papers`) remain **product decisions**, not blockers.
