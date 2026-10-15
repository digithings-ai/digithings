"""Destination of each workflow the repo split must not carry into a private repo.

Chris, 2026-10-14 (DIG-3605): no ``.github/workflows`` file moves into a private
repo. Each listed file is a Cloudflare cron, a local-ci job, or a deletion.
This module is that record. It does not deploy, and it does not call Cloudflare.

Deploy-type Worker workflows point at the signed-tag jobs in DIG-3697
(``scripts/deploy/<job>.sh``). Those scripts land with that PR; they are not
copied here. The two ``deploy-*-cloudflare.yml`` files are pull-request build
checks. Their live publish is Cloudflare Pages watching ``main``, so their
local-ci job is the build script, not a Worker deploy.
"""

from __future__ import annotations

from dataclasses import dataclass

DISPOSITIONS = ("cloudflare-cron", "local-ci", "deletion")


@dataclass(frozen=True)
class Row:
    """One listed path and the place its behaviour lives after the split."""

    repo: str
    path: str
    disposition: str
    clock_ids: tuple[str, ...] = ()
    anchor: str = ""
    anchor_lands_later: bool = False
    ci_uses: bool = False
    armed: bool = True
    note: str = ""


ROWS: tuple[Row, ...] = (
    Row(
        "R1",
        ".github/workflows/test-nautilus.yml",
        "local-ci",
        ci_uses=True,
        note="workflow_call lane from ci.yml. The runner design is DIG-3561.",
    ),
    Row(
        "R2",
        ".github/workflows/deploy-digiquant-runner.yml",
        "local-ci",
        anchor="scripts/deploy/runner.sh",
        anchor_lands_later=True,
        note="Signed-tag Worker job (DIG-3697). Live deploy stays disarmed there.",
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-digiquant.yml",
        "cloudflare-cron",
        clock_ids=("house-run-09",),
        note="Weekly house-run. The daily retries in jobs.ts stay disabled.",
    ),
    Row(
        "R2",
        ".github/digiquant-pipeline.yml",
        "cloudflare-cron",
        clock_ids=("house-run-09",),
        note="Tunables read by pipeline-digiquant.yml. Not a workflow.",
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-checkpoint-archive.yml",
        "cloudflare-cron",
        clock_ids=("checkpoint-archive",),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-market-data-refresh.yml",
        "cloudflare-cron",
        clock_ids=("market-data-refresh-morning", "market-data-refresh-evening"),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-research-metrics.yml",
        "cloudflare-cron",
        clock_ids=("research-metrics",),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-digiquant-prices.yml",
        "cloudflare-cron",
        clock_ids=(
            "prices-at-open-13",
            "prices-at-open-14",
            "prices-fx-refresh",
            "prices-fx-refresh-sun",
            "prices-eod-macro",
        ),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-digiquant-onchain.yml",
        "cloudflare-cron",
        clock_ids=("onchain",),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-digiquant-tearsheets.yml",
        "cloudflare-cron",
        clock_ids=("tearsheets",),
    ),
    Row(
        "R2",
        ".github/workflows/pipeline-digiquant-allocation-shadow.yml",
        "deletion",
        anchor="digiquant/scripts/research/check_allocation_shadow_isolation.py",
        note=(
            "workflow_run waits on 'Pipeline: dashboard research', which is not "
            "a workflow in this repo. The isolation script stays. DIG-3608 "
            "removes the workflow file."
        ),
    ),
    Row(
        "R2",
        ".github/workflows/sync-digiquant-runner-digikey-secret.yml",
        "local-ci",
        armed=False,
        note="Manual. Writes Worker secrets. This change adds no API call.",
    ),
    Row(
        "R2",
        ".github/workflows/sync-digiquant-runner-mail-secrets.yml",
        "local-ci",
        armed=False,
        note="Manual. Writes Worker secrets. This change adds no API call.",
    ),
    Row(
        "R2",
        ".github/workflows/test-digiquant.yml",
        "local-ci",
        ci_uses=True,
        note="workflow_call lane from ci.yml. The runner design is DIG-3561.",
    ),
    Row(
        "R3",
        ".github/workflows/deploy-digiquant-cloudflare.yml",
        "local-ci",
        anchor="scripts/build-digiquant.sh",
        note="Pull-request build check. Pages watching main is the publish.",
    ),
    Row(
        "R3",
        ".github/workflows/test-dashboard.yml",
        "local-ci",
        ci_uses=True,
        note="workflow_call lane from ci.yml. The runner design is DIG-3561.",
    ),
    Row(
        "R4",
        ".github/workflows/book-pdf.yml",
        "local-ci",
        anchor="apps/digithings-web/package.json",
        note="npm run book:pdf --workspace digithings-web.",
    ),
    Row(
        "R4",
        ".github/workflows/deploy-digithings-cloudflare.yml",
        "local-ci",
        anchor="scripts/build-digithings.sh",
        note="Pull-request build check. Pages watching main is the publish.",
    ),
    Row(
        "R4",
        ".github/workflows/refresh-repo-activity.yml",
        "cloudflare-cron",
        clock_ids=("refresh-repo-activity",),
    ),
    Row(
        "R4",
        ".github/workflows/test-web.yml",
        "local-ci",
        ci_uses=True,
        note="workflow_call lane from ci.yml. The runner design is DIG-3561.",
    ),
    Row(
        "R6",
        ".github/workflows/datatap-answer-check.yml",
        "cloudflare-cron",
        clock_ids=("datatap-answer-check",),
    ),
    Row(
        "R6",
        ".github/workflows/occ-invite-key-rollout.yml",
        "local-ci",
        anchor="scripts/check_occ_rollout_auth_guard.py",
        note="Guard script. The workflow_dispatch path is not a clock.",
    ),
    Row(
        "R5",
        ".github/workflows/deploy-digithings-cron.yml",
        "local-ci",
        anchor="scripts/deploy/cron.sh",
        anchor_lands_later=True,
        note="Signed-tag Worker job (DIG-3697). R5 rev 5 cron deploy.",
    ),
    Row(
        "R5",
        ".github/workflows/publish-digichat-image.yml",
        "local-ci",
        anchor="Dockerfile.digichat-cloudflare",
        note="Tag digichat-v*. Image publish, not the digichat Worker deploy.",
    ),
    Row(
        "R5",
        ".github/workflows/security-gitleaks.yml",
        "local-ci",
        anchor=".gitleaks.toml",
        note="R5 rev 5 gitleaks scan. Config stays; the workflow does not move.",
    ),
)


def by_path() -> dict[str, Row]:
    """Path to row. A duplicate path is a bug in the table, not a merge."""
    found: dict[str, Row] = {}
    for row in ROWS:
        if row.path in found:
            raise ValueError(f"duplicate map path: {row.path}")
        found[row.path] = row
    return found
