# Wave 1 — Phase P1 execution plan (monorepo + hosting)

This document **implements** [MIGRATION-ROADMAP-DIGITHINGS.md](MIGRATION-ROADMAP-DIGITHINGS.md) **§ P1 — Monorepo + hosting**. Complete [PRE-MIGRATION-CLEANUP.md](PRE-MIGRATION-CLEANUP.md) first so the tree you import is lean.

**DigiThings path:** sibling repo `../digithings` (see roadmap). There is **no** `apps/` folder in digithings today — Wave 1 **creates** the Atlas app location and wiring.

---

## Goals (from roadmap)

- Atlas **UI and build** live **inside** the DigiThings repo.
- **One** primary deploy story for that UI (staging first).
- **Optional:** keep GitHub Pages deploy from standalone `digiquant-atlas` until cutover, or retire it after parity.

**Acceptance:** Staging URL serves Atlas routes under a **sub-path** (e.g. `/atlas`); `NEXT_PUBLIC_*` only in client bundle; service role **server-only**.

---

## Naming (avoid collisions)

| In `digithings` | Already means | Atlas Wave 1 name |
|-----------------|---------------|-------------------|
| `digiquant/` | Nautilus backtest service | Do **not** reuse this folder for the Atlas web app. |
| `digichat/` | Next.js chat BFF | Atlas is a **separate** Next app or route tree — see below. |

**Recommended package path:** `apps/digiquant-atlas` **or** `apps/atlas-web` (pick one and use it in all docs/CI). The roadmap phrase “DigiQuant product” is **marketing**; the **directory** should say `digiquant-atlas` or `atlas` so it is not confused with `digiquant/`.

---

## Import strategy (pick one)

| Approach | Pros | Cons |
|----------|------|------|
| **Git subtree** | History preserved in monorepo | Larger clone; merge discipline |
| **Git submodule** | Atlas stays own remote | Two-repo workflow; CI must init submodule |
| **Copy + new root** | Simplest first deploy | Loses file-level history unless you squash |

For a **first** integration, **subtree** or **monorepo-native copy** with a clear tag in Atlas (`pre-digithings-import`) is enough; refine later.

**Minimum tree to import:**

- `frontend/` → becomes the Next app root under `apps/<name>/` (or merged layout).
- `supabase/migrations/`, `templates/`, `skills/`, `scripts/`, `config/` (non-secrets), `cowork/`, `docs/`, `.github/workflows` (adapt), `tests/` if present.

Do **not** import gitignored `data/`, `outputs/`, or local env files.

---

## Next.js integration options

DigiChat lives at `digichat/` (Next 16, App Router). Atlas `frontend/` is Next 15 + static export to `out/` today ([`deploy.yml`](../../.github/workflows/deploy.yml)).

| Option | Description |
|--------|-------------|
| **A — Standalone app in monorepo** | `apps/digiquant-atlas` full Next app; reverse proxy or host path `/atlas` → that service. Cleanest separation; matches roadmap “sub-route”. |
| **B — Route group under DigiChat** | `digichat/src/app/(atlas)/...` reuses one Next build. Faster coupling; mixes auth and Atlas concerns — only if you explicitly want one deployable. |

**Recommendation:** **Option A** for Wave 1 unless you need a single binary for demo week.

**`basePath`:** If served under `/atlas`, set `basePath: '/atlas'` in `next.config.ts` and fix any hardcoded absolute URLs in Atlas `frontend/`.

**Version alignment:** Plan a **Next/React bump** to match DigiChat (16 / 19) in the same Wave or immediately after first green build — track as a sub-task to avoid dual maintenance.

---

## Environment variables

| Variable | Client | Server / CI | Notes |
|----------|--------|-------------|--------|
| `NEXT_PUBLIC_SUPABASE_URL` | Yes | Build-time | Public |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Yes | Build-time | Public |
| `SUPABASE_SERVICE_ROLE_KEY` | **No** | Runner / server only | Never `NEXT_PUBLIC_*` |
| `STRIPE_*` | **No** until Wave 3 UI | BFF later | May omit in Wave 1 if no billing routes |
| `CRON_SECRET` | **No** | Internal triggers | Wave 2 graphs |

Copy patterns from [`config/local.env.example`](../../config/local.env.example) and [`RUNBOOK.md`](../../RUNBOOK.md). DigiThings centralizes secrets via **`.env`** / Compose (see `digithings/docker-compose.yml` patterns).

---

## CI / build

**Today:** Atlas uses [`.github/workflows/deploy.yml`](../../.github/workflows/deploy.yml) (Node 20, `frontend/`, static export).

**Wave 1:**

1. Add a **DigiThings** workflow (or `Makefile` target) that runs `npm ci && npm run build` in `apps/digiquant-atlas` (path TBD).
2. Decide **output:** static `out/` (Pages) vs **Node** `next start` behind Docker — DigiChat style suggests **server** deploy for BFF later; static export may limit future API routes.
3. **Smoke:** reuse [`scripts/smoke-test.sh`](../../scripts/smoke-test.sh) or a minimal `curl` health check against staging.

---

## Python / scripts (no relocation required for Wave 1)

Operators can keep running from **`digiquant-atlas` clone** or from monorepo path `apps/digiquant-atlas/../scripts` — document **`ATLAS_ROOT`** in DigiThings `.env.example` when scripts are invoked from containers.

Wave 1 **does not** require DigiGraph to run the pipeline; that is [Wave 2](DIGITHINGS-WAVE2-GRAPH-SKETCH.md).

---

## Ordered checklist

1. **Tag** current Atlas: `git tag pre-digithings-wave1` (optional).
2. **Create** `apps/<chosen-name>/` in `digithings`; import `frontend` + supporting dirs per table above.
3. **Adjust** `package.json` name, `next.config` `basePath`, TS paths if needed.
4. **Align** Node/npm versions with digithings (see root `Makefile` / `package.json` if present).
5. **Wire** env in Compose or hosting: `NEXT_PUBLIC_*` for build, secrets for server-only.
6. **Build** green locally from monorepo root.
7. **Add** CI job; artifact or image push per your deploy target.
8. **Deploy** staging; verify `/`, `/library`, `/portfolio` (or prefixed paths).
9. **Document** operator workflow: “clone digithings + branch” vs legacy standalone repo.
10. **Decide** GitHub Pages: keep dual deploy until cutover or redirect.

---

## Risks / decisions log

| Topic | Decision to record |
|-------|-------------------|
| Static `out/` vs SSR | Affects future Route Handlers for Wave 3 BFF |
| Next 15 → 16 | Schedule explicit upgrade task |
| Single vs dual repo during transition | Affects Cowork workspace path docs |

---

## Handoff to Wave 2

When P1 acceptance is met, proceed to roadmap **§ P1b** and [DIGITHINGS-WAVE2-GRAPH-SKETCH.md](DIGITHINGS-WAVE2-GRAPH-SKETCH.md). Graph runners will need a stable **`ATLAS_ROOT`** pointing at the monorepo path containing `scripts/`.
