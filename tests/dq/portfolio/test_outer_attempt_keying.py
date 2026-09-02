"""Per-attempt diagnostics keying (#1762).

``pipeline-digiquant.yml`` retries the chain up to 3 times inside ONE job, so every attempt sees
the same ``GITHUB_RUN_ID``. That was the whole upsert key, so the last attempt — usually the
cheap checkpoint-resumed one — replaced the expensive attempt's tokens and cost. 28 of the 54
rows in production carry a ``created_at`` that predates their own ``started_at``, which is only
possible if a prior insert was overwritten: ``_row()`` omits ``created_at``, so ON CONFLICT DO
UPDATE preserves the first insert's value while replacing every other column.

Run 29688378908 (2026-07-19) is the reference case: ``created_at`` 13:30:21 vs ``started_at``
13:35:25 — a 304s gap, which is ``OUTER_BACKOFF[1]=300`` plus process start — and the surviving
row claims 27 fresh baseline research segments from 1 LLM call in 55.6s for $0.0252, over a step
that ran 23m41s.
"""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.research.diagnostics import _row, summarize_run
from digiquant.research.state import ResearchState
from digiquant.portfolio.chain import OUTER_ATTEMPT_ENV, DiagnosticsDeps, _outer_attempt

pytestmark = pytest.mark.unit


class TestOuterAttemptFromEnv:
    def test_reads_the_workflow_counter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv(OUTER_ATTEMPT_ENV, "3")
        assert _outer_attempt() == 3

    def test_absent_env_is_attempt_one_not_the_legacy_sentinel(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A local or single-shot run genuinely IS the first attempt. 0 is reserved for rows
        migration 065 stamped as "written before per-attempt keying, provenance unknown", and
        conflating the two would relabel every local run as unknown."""
        monkeypatch.delenv(OUTER_ATTEMPT_ENV, raising=False)
        assert _outer_attempt() == 1

    @pytest.mark.parametrize("raw", ["", "   ", "two", "1.5", "0", "-2"])
    def test_a_malformed_value_degrades_to_one_rather_than_crashing(
        self, monkeypatch: pytest.MonkeyPatch, raw: str
    ) -> None:
        """This feeds telemetry. A bad env var must never be the reason a research run dies —
        at worst it re-collides two attempts the way the pre-#1762 code always did."""
        monkeypatch.setenv(OUTER_ATTEMPT_ENV, raw)
        assert _outer_attempt() == 1

    def test_deps_default_to_attempt_one(self) -> None:
        assert DiagnosticsDeps(client=None, run_id="123").attempt == 1


class TestTheRowCarriesTheAttempt:
    def _row_for(self, *, attempt: int) -> dict[str, object]:
        state = ResearchState(run_type="baseline", run_date=date(2026, 7, 19))
        return _row(
            run_id="29688378908",
            run_type="baseline",
            run_date=date(2026, 7, 19),
            model="gpt-x",
            usage_snapshot={"cost_usd": 0.025174, "total_tokens": 92725, "llm_calls": 1},
            summary=summarize_run(state),
            attempt=attempt,
        )

    def test_attempt_is_in_the_payload(self) -> None:
        assert self._row_for(attempt=2)["attempt"] == 2

    def test_two_attempts_of_one_run_differ_only_in_the_attempt_key(self) -> None:
        """The reason a composite key is sufficient: everything else about the row can be
        identical between attempts, so ``run_id`` alone cannot separate them."""
        first, second = self._row_for(attempt=1), self._row_for(attempt=2)
        assert first["run_id"] == second["run_id"]
        differing = {k for k in first if first[k] != second[k]}
        assert differing == {"attempt"}

    def test_created_at_is_not_in_the_payload(self) -> None:
        """Deliberately absent, and load-bearing for forensics rather than an oversight: it is
        what let the 28 overwritten rows be identified after the fact. Adding it would make a
        future collision invisible."""
        assert "created_at" not in self._row_for(attempt=1)

    def test_the_default_is_one_so_every_caller_is_safe(self) -> None:
        """``_row`` has other callers and tests; none of them should have to know about
        attempts, and none should silently produce the legacy 0 sentinel."""
        state = ResearchState(run_type="delta", run_date=date(2026, 7, 31))
        row = _row(
            run_id="r",
            run_type="delta",
            run_date=date(2026, 7, 31),
            model=None,
            usage_snapshot=None,
            summary=summarize_run(state),
        )
        assert row["attempt"] == 1
