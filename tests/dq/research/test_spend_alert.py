"""Spend alert (#1764) — alert only, never block.

Before this the only bound on a day's LLM spend was `pipeline-digiquant.yml`'s 240-minute
``timeout-minutes``. The owner's decision (2026-08-04) is **alert only**: record the breach and
surface it, but never abort a run and never refuse a segment — a mid-run abort would leave a
partially-published run, and #1749/#1751 established that partial states are where the silent
defects live.

So the load-bearing property here is a NEGATIVE one: no matter how large the spend, `status`,
`retry_signal` and the exit code must be untouched. Half these tests exist to pin that.

Calibration for the $10 default: production runs at $4.00 (07-31, 292 calls) and $4.70 (07-26,
349 calls), a ~$1.55 mean over the 22 rows whose telemetry was never overwritten, and the known
outlier at $11.95 (the Jun 19 delta run, RUNBOOK's own cost-governance example).
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.diagnostics import _row, summarize_run
from digiquant.research.state import AtlasResearchState
from digiquant.research.telemetry import (
    SPEND_ALERT_DEFAULT_USD,
    SPEND_ALERT_ENV,
    SPEND_ALERT_KEY,
    spend_alert,
    spend_alert_threshold_usd,
)

pytestmark = pytest.mark.unit


@pytest.fixture(autouse=True)
def _no_inherited_threshold(monkeypatch: pytest.MonkeyPatch) -> None:
    """The threshold is read from the process environment, so a stray value in the developer's
    shell would silently change what these tests measure."""
    monkeypatch.delenv(SPEND_ALERT_ENV, raising=False)


class TestThreshold:
    def test_default_sits_between_a_normal_day_and_the_known_outlier(self) -> None:
        """A deliberate tripwire on re-calibration, not an arbitrary range check.

        If the model roster is re-tiered and normal runs move to $12, this fails — and the right
        response is to re-derive the threshold from the new observed spend and update BOTH the
        constant and these bounds, not to widen the bounds until it goes green.
        """
        assert 4.70 < SPEND_ALERT_DEFAULT_USD < 11.95
        assert spend_alert_threshold_usd() == SPEND_ALERT_DEFAULT_USD

    def test_env_overrides(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(SPEND_ALERT_ENV, "2.5")
        assert spend_alert_threshold_usd() == 2.5

    @pytest.mark.parametrize("raw", ["0", "-1", "-0.5"])
    def test_zero_or_negative_disables_alerting(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        """An explicit off switch matters: this fires on a heuristic, and an operator running a
        deliberately expensive backfill must be able to silence it without editing code."""
        monkeypatch.setenv(SPEND_ALERT_ENV, raw)
        assert spend_alert_threshold_usd() is None
        assert spend_alert(10_000.0) is None

    @pytest.mark.parametrize("raw", ["ten", "", "   ", "$10"])
    def test_a_malformed_value_falls_back_to_the_default_rather_than_disabling(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        """Failing OPEN on a typo would silently remove the alert — the exact failure mode the
        alert exists to prevent. Fail toward alerting."""
        monkeypatch.setenv(SPEND_ALERT_ENV, raw)
        assert spend_alert_threshold_usd() == SPEND_ALERT_DEFAULT_USD


class TestTheAlertFragment:
    def test_fires_above_the_threshold(self) -> None:
        alert = spend_alert(11.95)
        assert alert is not None
        assert alert["est_cost_usd"] == 11.95
        assert alert["threshold_usd"] == SPEND_ALERT_DEFAULT_USD
        assert alert["scope"] == "invocation"

    @pytest.mark.parametrize("cost", [0.0, 1.55, 4.00, 4.70, SPEND_ALERT_DEFAULT_USD])
    def test_silent_at_or_below_the_threshold(self, cost: float) -> None:
        """Including exactly at the threshold — `>` not `>=`, so a threshold set to an observed
        value does not fire on that value."""
        assert spend_alert(cost) is None

    @pytest.mark.parametrize("cost", [None, "4.00", float("nan"), float("inf")])
    def test_a_non_numeric_or_non_finite_cost_is_silent_not_an_error(self, cost: object) -> None:
        """`usage_snapshot` is an untyped Mapping from a fail-soft accumulator, so `cost_usd` can
        be absent or junk."""
        assert spend_alert(cost) is None

    @pytest.mark.parametrize("cost", [True, False])
    def test_a_bool_is_rejected_rather_than_read_as_a_dollar_amount(
        self, monkeypatch: pytest.MonkeyPatch, cost: bool
    ) -> None:
        """`isinstance(True, int)` holds in Python, so without an explicit bool guard `True`
        would be read as $1.00.

        The threshold has to be dropped BELOW 1.0 for this test to mean anything: at the $10
        default, `True` returns None whether the guard exists or not — simply because 1 <= 10 —
        so the assertion would pass vacuously. Removing the guard and watching this test still
        pass is how that was found.
        """
        monkeypatch.setenv(SPEND_ALERT_ENV, "0.5")
        assert spend_alert(cost) is None


class TestItReachesTheDiagnosticsRow:
    def _row_for(self, cost: float | None) -> dict[str, object]:
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 8, 5))
        return _row(
            run_id="30930587340",
            run_type="delta",
            run_date=date(2026, 8, 5),
            model="gpt-x",
            usage_snapshot={"cost_usd": cost, "total_tokens": 1_840_000, "llm_calls": 292},
            summary=summarize_run(state),
            attempt=1,
        )

    def test_the_breakdown_carries_the_alert(self) -> None:
        row = self._row_for(18.42)
        breakdown = row["breakdown"]
        assert isinstance(breakdown, dict)
        assert breakdown[SPEND_ALERT_KEY]["est_cost_usd"] == 18.42

    def test_no_key_on_an_ordinary_day(self) -> None:
        """Absent, not false — matching `merge_fallback`, `content_freeze` and
        `circuit_breaker_skips`. The key's presence IS the signal."""
        breakdown = self._row_for(4.00)["breakdown"]
        assert isinstance(breakdown, dict)
        assert SPEND_ALERT_KEY not in breakdown

    def test_a_missing_cost_does_not_crash_the_row(self) -> None:
        breakdown = self._row_for(None)["breakdown"]
        assert isinstance(breakdown, dict)
        assert SPEND_ALERT_KEY not in breakdown


class TestItNeverBlocks:
    """The owner's decision, pinned. These are the tests that must never be relaxed."""

    def _summary_and_row(self, cost: float) -> tuple[object, dict[str, object]]:
        state = AtlasResearchState(run_type="delta", run_date=date(2026, 8, 5))
        summary = summarize_run(state)
        row = _row(
            run_id="r",
            run_type="delta",
            run_date=date(2026, 8, 5),
            model=None,
            usage_snapshot={"cost_usd": cost},
            summary=summary,
            attempt=1,
        )
        return summary, row

    def test_a_massive_overrun_leaves_status_untouched(self) -> None:
        _, row = self._summary_and_row(10_000.0)
        breakdown = row["breakdown"]
        assert isinstance(breakdown, dict)
        assert SPEND_ALERT_KEY in breakdown  # it did fire …
        baseline = summarize_run(AtlasResearchState(run_type="delta", run_date=date(2026, 8, 5)))
        assert row["status"] == baseline.status  # … and changed nothing

    def test_a_massive_overrun_leaves_retry_signal_untouched(self) -> None:
        """`retry_signal` drives the process exit code and therefore CI's outer-retry loop. An
        alert that flipped it would spend MORE money on a run flagged for spending too much."""
        summary, _ = self._summary_and_row(10_000.0)
        baseline = summarize_run(AtlasResearchState(run_type="delta", run_date=date(2026, 8, 5)))
        assert summary.retry_signal == baseline.retry_signal

    def test_the_alert_is_not_recorded_as_a_degraded_reason(self) -> None:
        """`breakdown.degraded_reasons` is what escalates `status`. Spend must not appear there."""
        _, row = self._summary_and_row(10_000.0)
        breakdown = row["breakdown"]
        assert isinstance(breakdown, dict)
        reasons = breakdown.get("degraded_reasons") or []
        assert not any("spend" in str(r).lower() for r in reasons)


class TestTheCIAnnotation:
    """A breakdown key and a log line are both passive. The annotation is what makes this an
    alert rather than a record — it shows on the run's summary page with nobody querying."""

    def _emit(
        self,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
        *,
        in_ci: bool,
        message: str,
    ) -> str:
        """Capture REAL stdout rather than patching ``print``.

        Patching ``builtins.print`` would only verify the test double. GitHub ignores a workflow
        command that is not line-initial, so what matters is the bytes that actually reach
        stdout — a stray prefix or leading whitespace is invisible to a mock.
        """
        from digiquant.research import diagnostics

        if in_ci:
            monkeypatch.setenv("GITHUB_ACTIONS", "true")
        else:
            monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        capsys.readouterr()  # drop anything emitted during setup
        diagnostics._emit_ci_warning(message)
        return capsys.readouterr().out

    def test_the_workflow_command_starts_its_own_line(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        out = self._emit(monkeypatch, capsys, in_ci=True, message="over budget")
        assert out.startswith("::warning::over budget")
        assert out.splitlines()[0].startswith("::warning::")
        assert out.endswith("\n")

    def test_silent_outside_actions(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A local run gets the ordinary log line and no stray workflow-command text on stdout.

        Also keeps `chain.py`'s `--dry-run` JSON-to-stdout clean — though that path returns
        before any diagnostics write, so it cannot reach here today.
        """
        assert self._emit(monkeypatch, capsys, in_ci=False, message="over budget") == ""

    def test_newlines_are_flattened_into_one_line(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """A newline terminates the workflow command: the annotation would truncate to its first
        line and the remainder would leak into the log as plain output."""
        out = self._emit(monkeypatch, capsys, in_ci=True, message="line one\nline two")
        assert out.count("\n") == 1  # the trailing one only
        assert "line two" in out.splitlines()[0]


class TestAnnouncingNeverCostsTheRow:
    """`_row` runs inside `write_row`'s fail-soft `try`. Announcing the alert therefore happens
    after the upsert and outside that block, so nothing raised while announcing can swallow the
    diagnostics write — an alert must never cost the row it annotates."""

    def test_announce_runs_after_the_upsert(self) -> None:
        import inspect

        from digiquant.research import diagnostics

        body = inspect.getsource(diagnostics.write_row)
        assert body.index(".upsert(") < body.index("_announce_spend_alert(")

    @pytest.mark.parametrize(
        "bad",
        [{}, {"breakdown": None}, {"breakdown": "nope"}, {"breakdown": {"spend_alert": 1}}],
    )
    def test_announce_swallows_a_malformed_row(self, bad: dict[str, object]) -> None:
        from digiquant.research import diagnostics

        diagnostics._announce_spend_alert(bad)  # must not raise

    def test_announce_emits_for_a_well_formed_alert(
        self, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from digiquant.research import diagnostics

        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        capsys.readouterr()
        diagnostics._announce_spend_alert(
            {"breakdown": {SPEND_ALERT_KEY: {"est_cost_usd": 18.42, "threshold_usd": 10.0}}}
        )
        out = capsys.readouterr().out
        assert out.startswith("::warning::")
        assert "18.42" in out and "10.00" in out
