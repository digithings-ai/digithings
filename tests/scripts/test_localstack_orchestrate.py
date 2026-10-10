"""Plan-construction and step-execution tests (DIG-2775, S7).

The plan must be honest in both directions: a step whose artefact belongs to
an unmerged sibling slice is SKIPPED, and a step that actually runs and exits
non-zero FAILS and stops the plan rather than marching on.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.localstack import orchestrate

pytestmark = pytest.mark.unit


# --- the plan is built from real commands, not placeholders ------------------


def test_up_plan_covers_the_eight_step_shape():
    names = [s.name for s in orchestrate.plan_up("core", {})]
    assert names == [
        "secrets-render",
        "supabase-start",
        "supabase-db-reset",
        "compose-up",
        "wrangler-dev",
        "reverse-proxy",
        "seed",
    ]


def test_compose_up_carries_the_requested_profile():
    step = next(s for s in orchestrate.plan_up("quant", {}) if s.name == "compose-up")
    assert "--profile" in step.argv and "quant" in step.argv


@pytest.mark.parametrize("profile", list(("core", "quant", "chat", "trace", "all")))
def test_every_profile_produces_a_compose_profile(profile):
    step = next(s for s in orchestrate.plan_up(profile, {}) if s.name == "compose-up")
    assert profile in step.argv


def test_reset_is_marked_destructive_and_runs_before_seeding():
    """The destructive step runs first, and the operator can see that it is."""
    steps = orchestrate.plan_reset({}, seed="42")
    assert [s.name for s in steps][0] == "supabase-db-reset"
    assert "DESTRUCTIVE" in steps[0].note.upper()
    assert "db reset" in " ".join(steps[0].argv)


def test_reset_passes_the_seed_through():
    steps = orchestrate.plan_reset({}, seed="42")
    seed_step = next(s for s in steps if s.name == "seed-all")
    assert "42" in seed_step.argv
    assert "--seed" in seed_step.argv


def test_seed_step_is_deterministic_by_default():
    assert "42" in orchestrate.plan_seed({}, seed="42")[-1].argv


def test_down_plan_keeps_volumes():
    """`down` must not destroy local data: no `-v`, no `supabase db reset`."""
    step = orchestrate.plan_down("core", {})[0]
    assert "-v" not in step.argv
    assert "--volumes" not in step.argv


def test_unknown_command_is_rejected():
    with pytest.raises(ValueError):
        orchestrate.steps_for("sideways", "core", {})


def test_a_tool_override_replaces_the_default_command():
    steps = orchestrate.plan_up("core", {"DT_COMPOSE_CMD": "podman compose"})
    step = next(s for s in steps if s.name == "compose-up")
    assert step.argv[0] == "podman"


# --- executing a step --------------------------------------------------------


def test_a_step_whose_artefact_is_absent_is_skipped_not_failed(tmp_path):
    """S5's script has not merged yet: skipping is the honest outcome."""
    step = orchestrate.Step(
        name="secrets-render", argv=("nope",), requires=("scripts/dt-secrets",), owner="S5"
    )
    outcome = orchestrate.run_step(step, tmp_path, {})

    assert outcome.status == "skipped"
    assert "not present" in outcome.detail
    assert "S5" in outcome.detail


def test_a_present_artefact_runs_the_command(tmp_path):
    (tmp_path / "scripts").mkdir()
    (tmp_path / "scripts" / "dt-secrets").write_text("", encoding="utf-8")
    seen = {}

    def runner(argv, cwd, env):
        seen["argv"] = tuple(argv)
        return 0, "rendered"

    step = orchestrate.Step(
        name="secrets-render", argv=("dt-secrets", "render"), requires=("scripts/dt-secrets",)
    )
    outcome = orchestrate.run_step(step, tmp_path, {}, runner=runner)

    assert outcome.status == "passed"
    assert seen["argv"] == ("dt-secrets", "render")


def test_a_non_zero_exit_is_a_failure(tmp_path):
    def runner(argv, cwd, env):
        return 2, "boom: no daemon"

    outcome = orchestrate.run_step(
        orchestrate.Step(name="compose-up", argv=("docker",)), tmp_path, {}, runner=runner
    )
    assert outcome.status == "failed"
    assert "2" in outcome.detail


def test_a_dry_run_runs_nothing(tmp_path):
    def runner(argv, cwd, env):  # pragma: no cover - must never be called
        raise AssertionError("a dry run must not execute a command")

    step = orchestrate.Step(name="supabase-start", argv=("supabase", "start"))
    outcome = orchestrate.run_step(step, tmp_path, {}, dry_run=True)

    assert outcome.status == "skipped"
    assert "dry-run" in outcome.detail
    assert "supabase start" in outcome.detail


def test_a_missing_binary_is_reported_not_raised(tmp_path):
    """A 127 from the shell is a failed step, not a traceback out of the plan."""
    outcome = orchestrate.run_step(
        orchestrate.Step(name="compose-up", argv=("definitely-not-a-real-binary",)),
        tmp_path,
        {},
        runner=orchestrate.subprocess_runner,
    )
    assert outcome.status == "failed"
    assert "127" in outcome.detail


def test_the_plan_stops_at_the_first_required_failure(tmp_path):
    """A later step assumes the earlier one ran; continuing would lie."""

    def runner(argv, cwd, env):
        return 1, "nope"

    steps = (
        orchestrate.Step(name="first", argv=("false",)),
        orchestrate.Step(name="second", argv=("true",)),
        orchestrate.Step(name="third", argv=("true",)),
    )
    report = orchestrate.run_steps("up", steps, tmp_path, {}, runner=runner)

    assert not report.ok
    assert [o.name for o in report.outcomes] == ["first"]


def test_an_optional_failure_does_not_stop_the_plan(tmp_path):
    def runner(argv, cwd, env):
        return 1, "optional step is unhappy"

    steps = (
        orchestrate.Step(name="optional", argv=("x",), optional=True),
        orchestrate.Step(name="required", argv=("y",)),
    )
    report = orchestrate.run_steps("up", steps, tmp_path, {}, runner=runner)

    assert [o.name for o in report.outcomes] == ["optional", "required"]
    assert not report.ok, "a failed optional step is still reported"


def test_a_skip_never_fails_the_plan(tmp_path):
    """A partial stack is normal while sibling slices are open."""
    steps = (
        orchestrate.Step(name="secrets", argv=("x",), requires=("scripts/dt-secrets",), owner="S5"),
        orchestrate.Step(name="supabase", argv=("y",)),
    )
    report = orchestrate.run_steps("up", steps, tmp_path, {}, dry_run=True)

    assert report.ok
    assert len(report.skipped) == 2


def test_the_report_json_carries_counts_for_ci():
    report = orchestrate.run_steps(
        "up", (orchestrate.Step(name="a", argv=("x",)),), Path("/tmp"), {}, dry_run=True
    )
    payload = report.to_dict()
    assert payload["counts"]["total"] == 1
    assert payload["counts"]["skipped"] == 1
    assert payload["dry_run"] is True
