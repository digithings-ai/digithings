""".github/workflows/db-migrate.yml must never record a migration it did not run (#1814).

The workflow applies pending Supabase migrations to prod on every push to ``main`` that
touches ``digiquant/supabase/migrations/**``, and ``olympus_schema_migrations`` is the only
record of what prod actually has. Until #1814 there was a second gate beside that ledger:
files whose numeric prefix was ``<= BASELINE_THROUGH`` (45) were INSERTed into the ledger
*without being executed*, on the theory that they predate the workflow.

That branch keyed on the filename prefix alone, so it could not tell "shipped before the
gate existed" from "merged this morning". ``037``, ``038`` and ``059`` are real unused gaps
in the chain, and back-filling one — the natural thing to do — produced a green run, a
ledger row claiming success, and no DDL on prod. That silent no-op is the failure mode
#1016 was opened to end. Meanwhile all 44 files ``<= 045`` were already ledgered, so the
branch was unreachable for every file that existed: it was deleted, not repaired.

These tests therefore assert on the **shape of the loop** rather than on the absence of the
string ``BASELINE_THROUGH``: the hole reopens just as easily under a different variable name
or an inlined ``[ "$num" -le 45 ]``. What is pinned is that the ledger lookup is the only
thing that can skip a file, that every ``INSERT INTO olympus_schema_migrations`` sits in a
branch that also feeds the file to psql, and — on the unwrapped path — that the INSERT
travels in the *same* psql invocation as the DDL, which is the whole of its atomicity.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "db-migrate.yml"

# Verbatim from the workflow. Every migration under digiquant/supabase/migrations/ is
# written against this exact test (see the headers of 060, 061, 063, 064), so it is a
# published contract, not an implementation detail.
SELF_WRAP_GREP = "grep -qiE '(^|[[:space:]])begin[[:space:]]*;'"

LEDGER_WRITE = re.compile(r"INSERT\s+INTO\s+olympus_schema_migrations", re.IGNORECASE)
FEEDS_FILE = re.compile(r"""(?:-f\s+"\$f"|cat\s+"\$f")""")


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def script(workflow: dict) -> str:
    """The applying step's shell body, with backslash-continuations folded into one line.

    Folding first is what lets "the same psql invocation" be asserted below by looking at a
    single line: the unwrapped path spans two physical lines but is one pipeline.
    """
    steps = workflow["jobs"]["migrate"]["steps"]
    bodies = [str(s["run"]) for s in steps if LEDGER_WRITE.search(str(s.get("run", "")))]
    assert len(bodies) == 1, f"expected one migration-applying step, found {len(bodies)}"
    return re.sub(r"\\\n\s*", " ", bodies[0])


@pytest.fixture(scope="module")
def loop(script: str) -> list[str]:
    """The body of the per-file loop, exclusive of `for`/`done`."""
    lines = script.splitlines()
    starts = [i for i, ln in enumerate(lines) if re.match(r"\s*for\s+f\s+in\b", ln)]
    ends = [i for i, ln in enumerate(lines) if ln.strip() == "done"]
    assert len(starts) == len(ends) == 1, "expected exactly one migration loop"
    return lines[starts[0] + 1 : ends[0]]


@pytest.fixture(scope="module")
def arms(loop: list[str]) -> dict[str, list[str]]:
    """The loop split at the self-wrapping grep: the run-up, each branch, and the tail.

    ``before`` is where a record-without-executing branch necessarily lives — it has to
    short-circuit ahead of both apply paths to avoid them — so keeping that region free of
    ledger writes is the load-bearing assertion in this file.
    """
    matches = [i for i, ln in enumerate(loop) if "grep -qiE" in ln]
    assert len(matches) == 1, "the self-wrapping BEGIN; grep is missing or duplicated"
    (i_if,) = matches
    i_else = next(i for i in range(i_if, len(loop)) if loop[i].strip() == "else")
    i_fi = next(i for i in range(i_else, len(loop)) if loop[i].strip() == "fi")
    return {
        "before": loop[:i_if],
        "self_wrapping": loop[i_if + 1 : i_else],
        "single_transaction": loop[i_else + 1 : i_fi],
        "after": loop[i_fi + 1 :],
    }


def _concurrency(workflow: dict) -> dict:
    """The workflow-level `concurrency:` mapping.

    Asserting the type here rather than indexing directly is what makes a revert to the
    scalar form (``concurrency: db-migrate``) fail with the reason instead of a TypeError.
    """
    concurrency = workflow["concurrency"]
    assert isinstance(concurrency, dict), (
        f"`concurrency: {concurrency}` is the scalar form, which cannot carry "
        "cancel-in-progress; a run left unapproved in `waiting` then holds the group "
        "indefinitely and starves every later run (#2541)"
    )
    return concurrency


def _uncommented(lines: list[str]) -> str:
    return "\n".join(ln for ln in lines if not ln.strip().startswith("#"))


def _guard(lines: list[str], idx: int) -> str:
    """What decides whether ``lines[idx]`` runs: its own `&&` test plus its enclosing `if`.

    Both forms have to be read because the guard has been written both ways — as
    ``[ -n "${exists}" ] && continue`` and as an ``if`` block — and the point of the
    assertion is the *condition*, not the syntax that carries it.
    """
    parts = [lines[idx]]
    depth = 0
    for j in range(idx - 1, -1, -1):
        stripped = lines[j].strip()
        if stripped == "fi":
            depth += 1
        elif stripped.startswith("if "):
            if depth == 0:
                parts.append(stripped)
                break
            depth -= 1
    return " ".join(parts)


# --------------------------------------------------------------------------- #
# The ledger is the only gate
# --------------------------------------------------------------------------- #


def test_no_baseline_style_env_key(workflow: dict) -> None:
    """A prefix threshold has to be configured somewhere; `env:` is where it lived."""
    scopes = [workflow.get("env") or {}]
    for job in workflow["jobs"].values():
        scopes.append(job.get("env") or {})
        for step in job.get("steps", []):
            scopes.append(step.get("env") or {})
    offenders = [
        k for scope in scopes for k in scope if re.search(r"baseline|grandfather", k, re.I)
    ]
    assert not offenders, (
        f"skip-execution threshold reintroduced as {offenders}; #1814 removed it because a "
        "migration merged today with a low prefix gets recorded and never run"
    )


def test_every_migration_file_reaches_the_loop_unfiltered(script: str) -> None:
    """Discovery is the blind spot of every assertion below: they only see the loop body.

    The exclusion can be reinstated one line *above* the loop and leave the suite green —
    ``find ... | sort | awk -F/ '$NF+0 > 45'``, or a pre-filtered ``PENDING`` array fed to
    the ``for`` — because a file that is never iterated is never applied *and* never
    recorded, and the loop that would have handled it correctly simply never sees it.

    So the pipeline that builds the list is pinned to shape: `find` over the migrations
    directory with no predicate beyond the `*.sql` name match, `sort` as the only stage
    after it, and the loop iterating that array. A `find` predicate and a pipeline filter
    are the same hole in different clothing, hence both halves.
    """
    lines = script.splitlines()
    discovery = [ln for ln in lines if "find digiquant/supabase/migrations" in ln]
    assert len(discovery) == 1, f"expected one migration-discovery command, got {len(discovery)}"
    stages = [stage.strip().rstrip(")").strip() for stage in discovery[0].split("|")]
    downstream = [stage.split()[0] for stage in stages[1:]]
    assert downstream == ["sort"], (
        f"stage(s) {downstream} sit between `find` and the loop; anything they drop is never "
        "applied and never recorded, and no assertion on the loop body can see it"
    )
    tokens = stages[0].partition("(")[2].split()
    assert tokens[:2] == ["find", "digiquant/supabase/migrations"], f"unexpected find: {tokens}"
    predicates = set(tokens[2:]) - {"-maxdepth", "1", "-name", "'*.sql'"}
    assert not predicates, (
        f"`find` predicate(s) {sorted(predicates)} can exclude a migration before the loop "
        "runs; the loop must be handed every .sql file in the directory"
    )
    header = next(ln for ln in lines if re.match(r"\s*for\s+f\s+in\b", ln))
    assert '"${FILES[@]}"' in header, (
        f"the loop no longer iterates the discovered files: {header.strip()!r} — a filtered "
        "copy of FILES reintroduces the #1814 hole one line above every assertion here"
    )


def test_only_the_ledger_lookup_can_skip_a_file(loop: list[str]) -> None:
    """Every early exit from the loop must be the `olympus_schema_migrations` check.

    A second skip path is the bug: it is reached only when the ledger has *no* row, i.e.
    exactly when the file still needs applying.
    """
    skips = [(i, _guard(loop, i)) for i, ln in enumerate(loop) if re.search(r"\bcontinue\b", ln)]
    assert skips, "nothing skips ledgered files any more; every push would replay all of prod"
    for i, guard in skips:
        assert "exists" in guard, (
            f"loop line {i} skips a migration on {guard.strip()!r}, which is not the ledger "
            "lookup — a file can now be passed over while prod has never run it"
        )


def test_the_loop_never_derives_a_number_from_the_filename(loop: list[str]) -> None:
    """The class of bug, not its one instance: prefix arithmetic has no legitimate use here.

    Ordering comes from `sort` over the whole filename and identity comes from the ledger
    key, so any numeric comparison in this loop is a threshold branch by another name.
    """
    body = _uncommented(loop)
    assert not re.search(r"-(?:le|lt|ge|gt)\b", body), "integer comparison in the migration loop"
    assert "10#" not in body, "base-10 prefix conversion in the migration loop"
    assert "%%_*" not in body, "numeric prefix extracted from the filename in the migration loop"


def test_the_ledger_lookup_precedes_every_apply(loop: list[str]) -> None:
    """Ordering is what made deleting the threshold safe, and nothing else guards it.

    The lookup short-circuits ledgered files before any branch below can act on them; put a
    branch first and it starts deciding the fate of files prod has already applied.
    """
    lookup = next(i for i, ln in enumerate(loop) if "SELECT 1 FROM olympus_schema_migrations" in ln)
    acts = [i for i, ln in enumerate(loop) if LEDGER_WRITE.search(ln) or FEEDS_FILE.search(ln)]
    assert acts, "the loop neither applies nor records anything"
    assert lookup < min(acts), "the loop applies or records a migration before checking the ledger"


# --------------------------------------------------------------------------- #
# Recorded implies executed
# --------------------------------------------------------------------------- #


def test_no_version_is_recorded_outside_an_applying_branch(arms: dict[str, list[str]]) -> None:
    """The #1814 finding, stated structurally: a ledger write must accompany a real apply."""
    for region in ("before", "after"):
        offenders = [ln.strip() for ln in arms[region] if LEDGER_WRITE.search(ln)]
        assert not offenders, (
            f"ledger write outside both apply branches ({region} the grep): {offenders} — this "
            "records a migration as applied without executing its DDL against prod"
        )
    for branch in ("self_wrapping", "single_transaction"):
        text = _uncommented(arms[branch])
        assert LEDGER_WRITE.search(text), f"{branch} branch applies a file it never records"
        assert FEEDS_FILE.search(text), f"{branch} branch records a file it never executes"


def test_the_unwrapped_path_bundles_the_insert_with_the_ddl(arms: dict[str, list[str]]) -> None:
    """One psql invocation, one transaction: the version is recorded iff the DDL commits.

    Split them into two calls and a failure between the two leaves prod migrated but the
    ledger silent, so the next run replays the file — and 060/063/064 are not idempotent
    under a replay of their GRANT/REVOKE and publication statements.
    """
    piped = [ln.strip() for ln in arms["single_transaction"] if "|" in ln and "psql" in ln]
    assert len(piped) == 1, f"expected one piped psql invocation, found {len(piped)}"
    (cmd,) = piped
    assert 'cat "$f"' in cmd, "the unwrapped path no longer feeds the migration file to psql"
    assert LEDGER_WRITE.search(cmd), "the ledger INSERT left the psql invocation that runs the DDL"
    assert "--single-transaction" in cmd, "the file and its ledger INSERT are no longer atomic"


def test_the_self_wrapping_path_runs_the_file_then_records_it(arms: dict[str, list[str]]) -> None:
    """A file carrying its own BEGIN; is atomic already; psql must not wrap it a second time."""
    calls = [ln.strip() for ln in arms["self_wrapping"] if "psql" in ln]
    assert len(calls) == 2, f"expected apply-then-record, found {len(calls)} psql call(s)"
    assert '-f "$f"' in calls[0], "the self-wrapping path no longer executes the migration file"
    assert LEDGER_WRITE.search(calls[1]), "the self-wrapping path no longer records the version"
    assert "--single-transaction" not in " ".join(calls), (
        "a migration with its own BEGIN; must not also be wrapped by psql --single-transaction"
    )


def test_the_begin_grep_is_verbatim_what_the_migrations_are_written_against(script: str) -> None:
    """Every migration header and its tests restate this regex; drift breaks that contract."""
    assert SELF_WRAP_GREP in script, "the BEGIN; detection regex changed"


def test_every_psql_call_that_writes_stops_on_error(script: str) -> None:
    """Without ON_ERROR_STOP psql exits 0 after a failed statement and the run goes green."""
    for ln in script.splitlines():
        if ln.strip().startswith("#") or "psql" not in ln:
            continue
        writes = "-f " in ln or LEDGER_WRITE.search(ln) or "CREATE TABLE" in ln
        if not writes:
            continue
        assert "-v ON_ERROR_STOP=1" in ln, f"psql write without ON_ERROR_STOP: {ln.strip()}"


def test_the_run_is_still_serialised_and_human_gated(workflow: dict) -> None:
    """Prod-mutating: the `production` environment carries the required-reviewer rule."""
    assert workflow["jobs"]["migrate"]["environment"] == "production"
    assert _concurrency(workflow)["group"] == "db-migrate", (
        "concurrent runs would race on the ledger"
    )
    # `on` is parsed as the boolean True by YAML 1.1.
    assert workflow[True]["push"]["branches"] == ["main"]
    assert workflow[True]["push"]["paths"] == ["digiquant/supabase/migrations/**"]


def test_an_unapproved_run_cannot_starve_every_later_one(workflow: dict) -> None:
    """#2541: this job holds the concurrency group while it waits for approval.

    The group has to stay — it is what keeps two applies off the ledger at once — but with
    `cancel-in-progress` absent (i.e. false) the run *occupying* the group is the one the
    setting protects, and this job occupies it for the whole time it sits in `production`'s
    required-reviewer gate. Run 31003345711 sat unapproved from 2026-08-05 to 08-20 and
    migrations 066-070 never reached prod. Each push in between was evicted from the
    group's single pending slot by its successor, so they report `cancelled` with zero
    jobs — which reads like somebody cancelled a deploy rather than like a deploy that
    never ran. That is why the failure went unnoticed for 15 days and why it is pinned
    here rather than left to a comment.

    Superseding is safe *because* of the ledger gate above: the loop iterates every `.sql`
    with no bound on count and no contiguity requirement, so the newest run's work is
    always a superset of what it displaces. Note the wrong fix, hence the last assertion:
    a `${{ }}` group such as ``db-migrate-${{ github.sha }}`` lets two applies race — the
    exact thing the group exists to prevent — and it does not even reliably end the
    starvation it was reached for, because two `workflow_dispatch` runs of an unchanged
    ref share the SHA and so share the group.
    """
    concurrency = _concurrency(workflow)
    assert concurrency.get("cancel-in-progress") is True, (
        "cancel-in-progress must be true, or a run left unapproved in `waiting` holds the "
        "group forever and every later push queues behind it — a silent outage of the only "
        "path to the prod schema, not a delay"
    )
    group = str(concurrency["group"])
    assert "${{" not in group, (
        f"group {group!r} varies per run, so applies no longer serialise at all; the fix "
        "for starvation is superseding within one group, never abandoning the group"
    )
