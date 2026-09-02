"""pipeline-olympus.yml must thread its retry counter into the process (#1762).

The workflow retries the chain up to ``MAX_OUTER_ATTEMPTS`` times inside ONE job, all sharing
one ``GITHUB_RUN_ID``. Since migration 065 the diagnostics row is keyed on
``(run_id, attempt)``, and the attempt number reaches Python through exactly one channel: the
``OLYMPUS_ATTEMPT`` environment variable exported by that loop.

**This is the failure mode these tests exist for.** If the export is dropped, renamed, or moved
outside the loop body, `chain._outer_attempt()` falls back to 1, every attempt collides on
``(run_id, 1)`` again, and the table looks *exactly* as it did before #1762 — the last attempt
overwriting the expensive one's cost. Nothing fails, nothing logs an error, and the only visible
symptom is a cost figure that is quietly a floor. That is the same silent-workflow-YAML class as
#1775 (a stale ``github.event.schedule`` literal disabling a cron job) and #1814 (a ledger row
for a migration that never ran), and it is guarded the same way.

Assertions are on the *shape* — the export must be inside the loop and must carry the loop's own
counter — rather than on the literal string, since the hole reopens just as easily under a
different variable name or an export hoisted above the loop where it would freeze at 1.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-olympus.yml"
CHAIN = REPO_ROOT / "digiquant" / "src" / "digiquant" / "olympus" / "hermes" / "chain.py"
DIAGNOSTICS = REPO_ROOT / "digiquant" / "src" / "digiquant" / "olympus" / "atlas" / "diagnostics.py"
MIGRATION = (
    REPO_ROOT / "digiquant" / "supabase" / "migrations" / "065_atlas_run_diagnostics_attempt.sql"
)


@pytest.fixture(scope="module")
def workflow_text() -> str:
    return WORKFLOW.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def retry_step(workflow_text: str) -> str:
    """The ``run:`` script of the step that contains the outer-retry loop."""
    doc = yaml.safe_load(workflow_text)
    scripts = [
        step["run"]
        for job in doc["jobs"].values()
        for step in job.get("steps", [])
        if isinstance(step, dict) and isinstance(step.get("run"), str)
        if "MAX_OUTER_ATTEMPTS" in step["run"]
    ]
    assert len(scripts) == 1, (
        f"expected exactly one step carrying the outer-retry loop, found {len(scripts)}; "
        "the fixture below assumes a single loop"
    )
    return scripts[0]


def _loop_body(script: str) -> str:
    """Everything from ``while`` to the loop's closing ``done``.

    Matches ``done`` on its own line at any indentation — yaml.safe_load has already stripped
    the block scalar's common indent, and pinning a literal depth made this brittle.
    """
    start = script.index("while ")
    match = re.search(r"^\s*done\s*$", script[start:], re.MULTILINE)
    assert match is not None, "could not find the loop's closing `done`"
    return script[start : start + match.start()]


class TestTheCounterReachesThePipeline:
    def test_the_attempt_is_exported(self, retry_step: str) -> None:
        assert "OLYMPUS_ATTEMPT" in retry_step, (
            "the retry loop must export OLYMPUS_ATTEMPT; without it every attempt's "
            "diagnostics row collides on (run_id, 1) and the last one overwrites the "
            "expensive attempt's cost — the #1762 defect, silently restored"
        )

    def test_the_export_carries_the_loop_counter_not_a_constant(self, retry_step: str) -> None:
        """A hard-coded ``OLYMPUS_ATTEMPT=1`` would satisfy the test above and fix nothing."""
        match = re.search(r"OLYMPUS_ATTEMPT=[\"']?\$\{?(\w+)", retry_step)
        assert match is not None, (
            "OLYMPUS_ATTEMPT must be assigned from a shell variable, not a literal"
        )
        var = match.group(1)
        assert re.search(rf"{var}=\$\(\({var} \+ 1\)\)", retry_step), (
            f"OLYMPUS_ATTEMPT is set from ${{{var}}}, but nothing increments {var} in this "
            "step — so it would report the same attempt number on every retry"
        )

    def test_the_export_is_inside_the_loop(self, retry_step: str) -> None:
        """Hoisted above the loop it would freeze at 1 — the collision, reintroduced."""
        assert "OLYMPUS_ATTEMPT" in _loop_body(retry_step), (
            "the OLYMPUS_ATTEMPT export must sit inside the while-loop body; outside it, the "
            "value is evaluated once and every attempt reports attempt 1"
        )

    def test_it_is_exported_not_just_assigned(self, retry_step: str) -> None:
        """The command runs through a pipe into ``tee``, so a bare assignment on the same
        logical line as the invocation would not necessarily reach the child."""
        assert re.search(r"export\s+OLYMPUS_ATTEMPT=", retry_step), (
            "use `export OLYMPUS_ATTEMPT=...`; a bare assignment does not reliably reach a "
            "command invoked through a pipeline"
        )

    def test_the_env_name_matches_what_chain_py_reads(self, retry_step: str) -> None:
        """The two halves are in different languages and different files — this is the only
        thing tying them together."""
        chain = CHAIN.read_text(encoding="utf-8")
        match = re.search(r'OUTER_ATTEMPT_ENV\s*=\s*"([^"]+)"', chain)
        assert match is not None, "chain.py must name the env var in OUTER_ATTEMPT_ENV"
        assert f"export {match.group(1)}=" in retry_step, (
            f"chain.py reads {match.group(1)!r} but the workflow does not export it"
        )


class TestTheKeyIsPerAttempt:
    def test_the_upsert_conflict_key_includes_attempt(self) -> None:
        text = DIAGNOSTICS.read_text(encoding="utf-8")
        assert 'on_conflict="run_id,attempt"' in text, (
            "the diagnostics upsert must conflict on (run_id, attempt); on run_id alone the "
            "last retry overwrites the earlier attempts (#1762)"
        )
        # Word-boundary regex, not a substring: `on_conflict="run_id"` is not a substring of
        # `on_conflict="run_id,attempt"` only because of the closing quote, and a reviewer
        # writing `"run_id, attempt"` with a space would slip past a naive check.
        assert not re.search(r'on_conflict="run_id"\s*\)', text), (
            "the run_id-only conflict key must be gone"
        )

    def test_created_at_is_still_omitted_from_the_row(self) -> None:
        """Deliberately unchanged. ``_row()`` omitting ``created_at`` is what made the old
        overwrite detectable at all — ON CONFLICT DO UPDATE preserved the first insert's value
        while replacing everything else, which is how the 28 corrupted rows were identified.
        Adding it would erase the forensic signal for any future collision."""
        text = DIAGNOSTICS.read_text(encoding="utf-8")
        row_start = text.index("def _row(")
        row_end = text.index("\ndef ", row_start + 1)
        assert '"created_at"' not in text[row_start:row_end]


class TestTheMigrationMatchesTheCode:
    def test_the_migration_exists_and_adds_the_column(self) -> None:
        sql = MIGRATION.read_text(encoding="utf-8")
        assert "ADD COLUMN IF NOT EXISTS attempt integer" in sql
        assert "PRIMARY KEY (run_id, attempt)" in sql

    def test_legacy_rows_are_stamped_with_a_sentinel_not_one(self) -> None:
        """Backfilling ``1`` would assert that 28 provably-collapsed rows are first attempts."""
        sql = MIGRATION.read_text(encoding="utf-8")
        assert "DEFAULT 0" in sql, "pre-existing rows must get the 0 sentinel, never 1"
        assert "DEFAULT 1" not in sql

    def test_the_migration_is_unwrapped(self) -> None:
        """db-migrate.yml runs an unwrapped file and its ledger INSERT in ONE
        --single-transaction psql call, so the version is recorded iff the DDL commits. A
        self-wrapped file takes the two-call path, where a crash between them leaves prod
        migrated with a silent ledger.

        This mirrors the workflow's own detector *including its flaw*: the grep runs over the
        raw file and does not strip comments, so prose containing the transaction-start keyword
        followed by a semicolon reroutes the migration onto the non-atomic path. That is not
        hypothetical — the first draft of 065 tripped it from an explanatory comment, and this
        assertion is what caught it. Keep the pattern identical to db-migrate.yml's.
        """
        sql = MIGRATION.read_text(encoding="utf-8")
        assert not re.search(r"(^|\s)begin\s*;", sql, re.IGNORECASE), (
            "db-migrate.yml would classify this file as self-wrapping and take the two-call, "
            "non-atomic path — even if the match is inside a comment"
        )

    def test_the_view_appends_attempt_last(self) -> None:
        """CREATE OR REPLACE VIEW can only append columns. Slotting ``attempt`` next to
        ``run_id`` — the natural reading order — fails with 'cannot change name of view
        column' and takes the whole migration down inside a db-migrate run."""
        sql = MIGRATION.read_text(encoding="utf-8")
        view = sql[sql.index("CREATE OR REPLACE VIEW") :]
        select_list = view[view.index("SELECT") : view.index("FROM public.atlas_run_diagnostics")]
        columns = [c.strip() for c in select_list.removeprefix("SELECT").split(",") if c.strip()]
        assert columns[-1] == "attempt", f"attempt must be the last column, got {columns}"
        assert columns[:-1] == [
            "run_id",
            "run_date",
            "run_type",
            "model",
            "status",
            "started_at",
            "finished_at",
            "duration_s",
            "segments_total",
            "segments_ok",
            "segments_carried",
            "segments_failed",
            "created_at",
        ], "the pre-existing column order must be preserved exactly, or the REPLACE fails"


class TestOpenrouterFallbackModelsPinnedTogether:
  """Preflight and pipeline steps must share the same OPENROUTER_FALLBACK_MODELS pool (#2523)."""

  def test_preflight_and_pipeline_steps_share_fallback_pool(self) -> None:
      doc = yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))
      steps = [
          step
          for job in doc["jobs"].values()
          for step in job.get("steps", [])
          if isinstance(step, dict) and step.get("env", {}).get("OPENROUTER_FALLBACK_MODELS")
      ]
      names = [step.get("name", "<unnamed>") for step in steps]
      pools = [step["env"]["OPENROUTER_FALLBACK_MODELS"] for step in steps]
      assert len(pools) == 2, (
          f"expected exactly two OPENROUTER_FALLBACK_MODELS env entries, found {len(pools)} "
          f"on steps {names}"
      )
      assert pools[0] == pools[1], (
          "preflight and pipeline steps must share the same fallback pool; edit one without "
          "the other and the preflight silently tests stricter routing than the real run"
      )
