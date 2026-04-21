#!/usr/bin/env python3
"""File child tasks for epics #295, #296, #297.

One-shot. Re-running would create duplicates — check before re-run.
"""
import subprocess, sys, textwrap

REPO = "digithings-ai/digithings"

TASKS = [
    # ---- Epic #295: Atlas daily-update backend ----
    {
        "parent": 295, "slug": "295-publish",
        "title": "[agent] Atlas daily snapshot publish — JSON artifact consumable by frontend",
        "labels": "agent-task,component:digiquant,priority:high,complexity:S,type:feature,risk:low",
        "goal": "After the daily pipeline recomputes outputs, publish a single JSON snapshot at a stable, frontend-consumable location (object store path, committed data branch, or signed URL). Atlas frontend reads this snapshot to render the daily view.",
        "accept": [
            "Publish step runs as the final stage of the daily pipeline.",
            "Snapshot schema documented (Pydantic v2 model in `digiquant/src/digiquant/atlas/snapshot.py` or equivalent).",
            "Snapshot path/URL documented in `apps/digiquant-atlas/ARCHITECTURE.md`.",
            "Snapshot is versioned (filename or manifest includes date + schema version).",
            "Frontend can fetch and parse it without auth (or with a documented public read token).",
        ],
        "docs": "apps/digiquant-atlas/ARCHITECTURE.md; digiquant/docs/ if schema lives there.",
    },
    {
        "parent": 295, "slug": "295-frontend-wire",
        "title": "[agent] Atlas frontend reads daily snapshot — replace stubs/mocks",
        "labels": "agent-task,component:digiquant,priority:high,complexity:M,type:feature,risk:low",
        "goal": "Atlas Next.js frontend reads the published daily snapshot and renders it. No stub data, no placeholders, no hardcoded mock fixtures in production paths.",
        "accept": [
            "Frontend fetches the snapshot at load time, handles loading + error states.",
            "Every visible data element traces to a snapshot field (no mock leftovers).",
            "Type-safe: TS interfaces generated from or aligned with the Pydantic schema.",
            "Playwright/Vitest smoke test: mount the page against a fixture snapshot and assert it renders.",
            "Empty-state handling: if snapshot is missing or stale > 48h, user sees a clear 'stale' banner.",
        ],
        "docs": "apps/digiquant-atlas/frontend/README.md; frontend README after move to frontend/atlas/.",
    },
    {
        "parent": 295, "slug": "295-alerting",
        "title": "[agent] Atlas daily job — failure alerting",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:S,type:infra,risk:low",
        "goal": "When the daily GHA job (#298) fails, a human is notified within one business day. Minimum bar: GitHub Actions failure visible + email-style notification.",
        "accept": [
            "Workflow failure triggers a GitHub issue comment on a tracking issue, OR posts to a Slack/Discord webhook, OR both.",
            "Alert includes run URL, failing step, and last successful run timestamp.",
            "Documented on-call path: who sees the alert and what they do (short runbook).",
            "Tested by intentionally failing a workflow_dispatch run.",
        ],
        "docs": "apps/digiquant-atlas/RUNBOOK.md.",
    },

    # ---- Epic #296: Atlas user profiling ----
    {
        "parent": 296, "slug": "296-schema-profile",
        "title": "[agent] Investment-profile schema — Pydantic v2, versioned",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:M,type:feature,risk:low",
        "goal": "Define the data model for a user investment profile: risk tolerance, horizon, liquidity needs, base currency, coarse tax jurisdiction, ESG preferences, excluded sectors, experience level. Versioned so future migrations are tractable.",
        "accept": [
            "Pydantic v2 model with field validators.",
            "Schema version field (e.g., `schema_version: int = 1`).",
            "Example profile fixture checked in.",
            "Unit tests: valid profile round-trips JSON; invalid profiles raise on the expected field.",
            "Schema JSON exported to `digiquant/docs/schemas/investment_profile.v1.json`.",
        ],
        "docs": "digiquant/docs/profiles/README.md (new).",
    },
    {
        "parent": 296, "slug": "296-schema-assets",
        "title": "[agent] Asset-preferences schema — watchlists, custom universe, exclusions",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:S,type:feature,risk:low",
        "goal": "Companion schema to the investment profile: per-user watchlists, a custom asset universe (tickers/ETFs), and exclusion lists (tickers/sectors). Separate from the profile because it mutates more often.",
        "accept": [
            "Pydantic v2 model with normalization (upper-case tickers, de-dupe).",
            "Schema version field.",
            "Unit tests: valid/invalid cases; exclusion wins over inclusion on conflict.",
            "Example fixture.",
        ],
        "docs": "digiquant/docs/profiles/README.md.",
    },
    {
        "parent": 296, "slug": "296-persistence",
        "title": "[agent] Profile persistence — per-user storage backend (DigiKey-adjacent initially)",
        "labels": "agent-task,component:digikey,priority:medium,complexity:M,type:feature,risk:med",
        "goal": "Store and retrieve per-user investment profiles and asset preferences. Initial backend lives alongside DigiKey (shares identity boundary); migrate to DigiStore when that module lands (#172).",
        "accept": [
            "CRUD API: create, read, update, (soft-)delete profile + asset-prefs by user id.",
            "Row-level isolation: a user can only read/write their own records.",
            "Audit: writes emit `digibase.audit` events with PII redaction.",
            "Unit tests cover happy path + authz negatives.",
            "Migration path to DigiStore documented (ADR or plan file).",
        ],
        "docs": "digikey/ARCHITECTURE.md (new section); digiquant/docs/profiles/README.md.",
    },
    {
        "parent": 296, "slug": "296-jwt-claims",
        "title": "[agent] Profile claims on DigiKey JWTs — profile_id and profile_version",
        "labels": "agent-task,component:digikey,priority:medium,complexity:S,type:feature,risk:med",
        "goal": "DigiKey JWTs carry minimal profile pointers (`profile_id`, `profile_version`) so downstream services (Atlas, DigiGraph) can key off the authenticated user without a second DB lookup.",
        "accept": [
            "Claim schema documented in `digikey/ARCHITECTURE.md`.",
            "JWTs minted post-login include the claims when a profile exists.",
            "Missing-profile case: claims absent, frontend routes user to intake flow.",
            "Unit tests: claim present after profile create; claim bumps on profile update.",
        ],
        "docs": "digikey/ARCHITECTURE.md.",
    },
    {
        "parent": 296, "slug": "296-intake-subgraph",
        "title": "[agent] DigiChat intake sub-graph — guided profile-building conversation",
        "labels": "agent-task,component:digigraph,priority:medium,complexity:L,type:feature,risk:med",
        "goal": "A LangGraph sub-graph that walks a user through a 5–8 minute conversation and emits a complete `InvestmentProfile` via Pydantic v2 structured outputs. Asks clarifying follow-ups on ambiguous answers.",
        "accept": [
            "Sub-graph registered in `digigraph/orchestration/registry.py` per sub-graph registry pattern.",
            "Structured-output node returns a validated `InvestmentProfile` v1.",
            "Conversation covers: risk, horizon, liquidity, base currency, ESG, exclusions, experience.",
            "Unit tests with canned model responses (LiteLLM test mode) verify the graph reaches completion on a golden transcript.",
            "Saves profile via the persistence API on completion (#296-persistence).",
        ],
        "docs": "digigraph/ARCHITECTURE.md; digigraph/docs/subgraphs/intake.md (new).",
    },
    {
        "parent": 296, "slug": "296-intake-ui",
        "title": "[agent] DigiChat UI for profile intake — entry CTA, progress, review screen",
        "labels": "agent-task,component:digichat,priority:medium,complexity:M,type:feature,risk:low",
        "goal": "User-facing surface in DigiChat for running the intake sub-graph: 'Set up your profile' CTA on first login, inline progress during the conversation, a review-and-edit screen before final submit.",
        "accept": [
            "New route or panel in DigiChat that kicks the intake sub-graph.",
            "Progress indicator (e.g., step N of M) visible during intake.",
            "Pre-submit review screen lets user edit any field.",
            "On submit, profile is persisted and user returns to the main chat.",
            "Vitest/Playwright smoke test on the review screen.",
        ],
        "docs": "frontend/digichat/README.md.",
    },
    {
        "parent": 296, "slug": "296-revision",
        "title": "[agent] Profile revision flow — re-run intake or edit fields directly",
        "labels": "agent-task,component:digichat,priority:low,complexity:S,type:feature,risk:low",
        "goal": "Users can update their profile after initial setup — either by re-running intake or editing the fields directly in a settings panel.",
        "accept": [
            "Settings panel lists current profile fields, editable in place.",
            "'Redo intake' button re-runs the sub-graph prefilled with current values.",
            "Edits bump `profile_version` and trigger JWT refresh on next request.",
            "Unit test: edit → persist → JWT claim version increments.",
        ],
        "docs": "frontend/digichat/README.md.",
    },
    {
        "parent": 296, "slug": "296-atlas-reads-profile",
        "title": "[agent] Atlas filters and ranks daily output by user profile",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:M,type:feature,risk:low",
        "goal": "Logged-in Atlas users see a view filtered by their profile: custom universe honored, exclusions applied, ranking weighted by risk/horizon preferences.",
        "accept": [
            "Atlas snapshot rendering path takes a profile and returns a personalized view.",
            "Anonymous users see the global default view (current behavior).",
            "Filter + rank logic unit-tested against fixture profiles.",
            "Performance: personalization adds < 100 ms to page render.",
        ],
        "docs": "apps/digiquant-atlas/ARCHITECTURE.md.",
    },
    {
        "parent": 296, "slug": "296-custom-research",
        "title": "[agent] Custom research trigger — user-requested one-off research run",
        "labels": "agent-task,component:digiquant,priority:low,complexity:L,type:feature,risk:med",
        "goal": "From Atlas, a user can submit a prompt scoped to their profile; the system runs a research job and delivers results back (in Atlas, email, or notification).",
        "accept": [
            "UI entry point: a 'Run custom research' button with a prompt field.",
            "Backend queues a job keyed to user + profile + prompt.",
            "Job executes via DigiGraph research sub-graph (existing or #186/#187).",
            "Results land in a user-scoped location in Atlas (new 'My research' section) and optionally trigger email/webhook.",
            "Rate-limited per user (config-driven).",
        ],
        "docs": "apps/digiquant-atlas/ARCHITECTURE.md; digigraph/docs/subgraphs/.",
    },

    # ---- Epic #297: Atlas into digiquant migration ----
    {
        "parent": 297, "slug": "297-adr",
        "title": "[agent] ADR — Atlas belongs in digiquant/, not apps/",
        "labels": "agent-task,component:root,priority:high,complexity:S,type:research,risk:low",
        "goal": "File ADR-00XX that reverses the `apps/digiquant-atlas/` pattern: Atlas is a DigiQuant product and lives inside the module. Captures the rationale (product family coherence, frontend-umbrella alignment, tooling de-duplication) and the phased migration plan.",
        "accept": [
            "ADR drafted in `docs/adr/00XX-atlas-in-digiquant.md` following the existing ADR template.",
            "Status: Accepted (once merged).",
            "Cross-references ADR-0009 (frontend umbrella).",
            "Lists the phases and their owning child issues.",
        ],
        "docs": "docs/adr/00XX-atlas-in-digiquant.md (new).",
    },
    {
        "parent": 297, "slug": "297-python-move",
        "title": "[agent] Atlas Python package move — digiquant_atlas → digiquant.atlas",
        "labels": "agent-task,component:digiquant,priority:high,complexity:L,type:migration,risk:med",
        "goal": "Move `apps/digiquant-atlas/src/digiquant_atlas/` to `digiquant/src/digiquant/atlas/`. Hard cut on import root (no shim, per pre-1.0 decision). Update all callers: scripts, tests, skill manifests.",
        "accept": [
            "New path: `digiquant/src/digiquant/atlas/` contains all former `digiquant_atlas` code.",
            "All imports updated from `digiquant_atlas` → `digiquant.atlas`.",
            "`digiquant/pyproject.toml` includes the new subpackage.",
            "All Atlas unit tests pass against the new layout.",
            "`pytest -m unit -k atlas` green.",
        ],
        "docs": "digiquant/ARCHITECTURE.md; digiquant/AGENTS.md.",
    },
    {
        "parent": 297, "slug": "297-docs-move",
        "title": "[agent] Move Atlas docs, config, scripts into digiquant/",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:M,type:migration,risk:low",
        "goal": "Move `apps/digiquant-atlas/docs/`, `config/`, and `scripts/` into sensible homes under `digiquant/`. Docs → `digiquant/docs/atlas/`; config → `digiquant/config/atlas/`; scripts → `digiquant/scripts/atlas/`.",
        "accept": [
            "All three trees moved; no content lost.",
            "Internal links updated (ripgrep for old paths → zero hits).",
            "CLAUDE.md and AGENTS.md updated.",
            "`make doc-check` passes.",
        ],
        "docs": "CLAUDE.md; AGENTS.md; digiquant/AGENTS.md.",
    },
    {
        "parent": 297, "slug": "297-supabase-move",
        "title": "[agent] Move Atlas supabase migrations into digiquant/supabase/",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:S,type:migration,risk:med",
        "goal": "Relocate `apps/digiquant-atlas/supabase/migrations/` to `digiquant/supabase/migrations/`. No schema changes — paths only.",
        "accept": [
            "Migrations run cleanly from the new location against a fresh dev DB.",
            "Supabase CLI config (if any) updated.",
            "CI step (if any) references the new path.",
            "Production migration instructions documented (no-op expected — path is dev-local).",
        ],
        "docs": "digiquant/ARCHITECTURE.md (data section).",
    },
    {
        "parent": 297, "slug": "297-skills-agent-surface",
        "title": "[agent] Consolidate Atlas skills and agent surface under digiquant/",
        "labels": "agent-task,component:digiquant,priority:medium,complexity:M,type:migration,risk:low",
        "goal": "Atlas's 40+ skills move to `digiquant/atlas/skills/`. Its private `.claude/`, `.cursor/`, `.agents/` surfaces are reconciled with the monorepo root: content merged where non-duplicated, deleted otherwise.",
        "accept": [
            "Skills tree at `digiquant/atlas/skills/`.",
            "No duplicate skill definitions between Atlas's old surface and the monorepo root `.claude/`.",
            "`make agents-init` idempotent (CI `scripts/agents_init.py --check` passes).",
            "Agent instructions point at new paths.",
        ],
        "docs": "AGENTS.md; digiquant/AGENTS.md; .claude/ via agents-init.",
    },
    {
        "parent": 297, "slug": "297-ci-fold",
        "title": "[agent] Fold Atlas .github/workflows/ into monorepo root",
        "labels": "agent-task,component:root,priority:medium,complexity:M,type:infra,risk:med",
        "goal": "Atlas's own workflows under `apps/digiquant-atlas/.github/workflows/` move to the monorepo root `.github/workflows/` as `atlas-*.yml`. Reconcile with existing `digiquant-*.yml` — Atlas tests become part of the digiquant test matrix where sensible.",
        "accept": [
            "All Atlas workflows relocated, renamed `atlas-*.yml`.",
            "No duplication with existing `digiquant-test.yml`, `digiquant-prices.yml`.",
            "CI green on a workflow_dispatch of each migrated workflow.",
            "Old Atlas workflow tree deleted.",
        ],
        "docs": "CLAUDE.md (commands section if affected); AGENTS.md.",
    },
    {
        "parent": 297, "slug": "297-cleanup",
        "title": "[agent] Delete apps/digiquant-atlas/ shell and finalize migration",
        "labels": "agent-task,component:root,priority:medium,complexity:S,type:migration,risk:low",
        "goal": "After all phases land, delete the `apps/digiquant-atlas/` directory (or reduce to a one-line README pointing to `digiquant/`). Final sweep: CLAUDE.md, ARCHITECTURE.md, docs/VISION.md, memory files.",
        "accept": [
            "`apps/digiquant-atlas/` removed (or a trivial redirect README).",
            "`rg -F 'apps/digiquant-atlas' docs/ *.md` returns zero results (or only intentional historical references in ADRs).",
            "CLAUDE.md Atlas references point at `digiquant/`.",
            "docs/VISION.md updated if it used the old path.",
            "Memory update note added for future agents.",
        ],
        "docs": "CLAUDE.md; ARCHITECTURE.md; docs/VISION.md.",
    },
]


def build_body(task: dict) -> str:
    accept = "\n".join(f"- [ ] {a}" for a in task["accept"])
    return textwrap.dedent(f"""
        ## Goal

        {task['goal']}

        ## Acceptance criteria

        {accept}

        ## Documentation

        {task['docs']}

        ## Parent

        Part of #{task['parent']}.
        """).strip()


def main():
    dry_run = "--apply" not in sys.argv
    if dry_run:
        print("DRY RUN. Pass --apply to actually file.")
    for t in TASKS:
        body = build_body(t)
        cmd = [
            "gh", "issue", "create", "--repo", REPO,
            "--title", t["title"],
            "--label", t["labels"],
            "--body", body,
        ]
        print(f"→ {t['title']}")
        if not dry_run:
            r = subprocess.run(cmd, capture_output=True, text=True)
            if r.returncode != 0:
                print(f"  FAIL: {r.stderr.strip()}")
                sys.exit(1)
            print(f"  {r.stdout.strip()}")


if __name__ == "__main__":
    main()
