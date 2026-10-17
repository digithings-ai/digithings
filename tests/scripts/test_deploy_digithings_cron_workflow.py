"""The cron deploy lane is a gated production lane, not a develop push (DIG-3129).

``deploy-digithings-cron.yml`` publishes the org-wide production clocks Worker. Until
DIG-3129 it was push-triggered on ``[develop, main]`` and gated on ``environment: cron`` —
an environment with no required reviewers and no branch policy, so the gate was inert and
any push touching ``apps/digithings-cron/**`` deployed production. The promotion that
carries the clock rewrite (37 → 43 expressions) would have published it on that ungated
lane on the first ``main`` push.

The shape is now the one ``deploy-digiquant-runner.yml`` already had, and this pins it:
``main`` is the only deploy ref, the ``deploy`` job sits behind ``environment: production``
(whose reviewer and main-only branch policy already exist), and the workflow still has no
``schedule`` key (the clocks live on the Worker, not in GHA). A change on ``develop`` is
validated by the CI ``web`` lane and ``build-cloudflare-workers.yml`` and reaches
production only through a promotion into ``main``.

These are asserted structurally, over the workflow's own document, because a re-added
``develop`` branch or a dropped ``environment:`` is valid YAML that lints clean and would
still ship.
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "deploy-digithings-cron.yml"

#: A concurrency group carrying one of these is unique per run, so a run held at the
#: ``production`` approval gate cannot queue a later deploy behind it (#2541).
PER_RUN_TOKENS = ("github.run_id", "github.run_number")


def _doc() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _triggers(doc: dict) -> dict:
    """``on:`` — YAML 1.1 parses a bare ``on`` key as the boolean ``True``."""
    raw = doc.get("on", doc.get(True))
    assert isinstance(raw, dict), "workflow has no trigger mapping"
    return raw


def _job(doc: dict) -> dict:
    jobs = doc["jobs"]
    assert len(jobs) == 1, "the lane must stay a single job"
    return next(iter(jobs.values()))


def test_main_is_the_only_deploy_ref() -> None:
    """A push to ``develop`` must not deploy this Worker to production."""
    push = _triggers(_doc()).get("push")
    assert isinstance(push, dict), "the lane must keep a push trigger on main"
    assert push.get("branches") == ["main"], (
        "the cron deploy must fire on `main` only: a develop push here is a production "
        "deploy, which is the ungated lane DIG-3129 closed"
    )
    assert "develop" not in (push.get("branches") or [])


def test_the_manual_trigger_is_kept() -> None:
    """The lane must stay manually trippable for an operator deploy."""
    assert "workflow_dispatch" in _triggers(_doc())


def test_the_deploy_job_is_gated_on_production() -> None:
    """The deploy must wait on the ``production`` environment's reviewer gate.

    ``production`` is the environment with ``required_reviewers`` and a ``main``-only
    branch policy; ``cron`` has neither, so gating on it gates nothing.
    """
    environment = _job(_doc()).get("environment")
    name = environment["name"] if isinstance(environment, dict) else environment
    assert name == "production", (
        "the cron deploy must declare `environment: production`, the only environment "
        "with a reviewer and a main-only branch policy"
    )


def test_the_gated_job_never_queues() -> None:
    """A per-run concurrency group, so a held run cannot starve later deploys (#2541).

    The parametrised sweep in ``test_workflow_environment_concurrency.py`` also covers
    this; it is pinned here so the lane's own shape is legible without reading that file.
    """
    concurrency = _doc().get("concurrency")
    assert isinstance(concurrency, dict), "a scalar concurrency cannot carry cancel-in-progress"
    group = str(concurrency.get("group", ""))
    cancels = concurrency.get("cancel-in-progress") is True
    assert cancels or any(token in group for token in PER_RUN_TOKENS), (
        "a production-gated deploy needs a per-run concurrency group (or "
        "cancel-in-progress: true), or an unapproved run stops the workflow (#2541)"
    )


def test_no_gha_schedule_key() -> None:
    """The Worker owns the clocks; a GHA ``schedule`` here would double-fire them."""
    assert "schedule" not in _triggers(_doc())
