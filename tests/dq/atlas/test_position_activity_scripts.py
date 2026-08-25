"""Regression tests for the Atlas Activity repair script paths (#1928)."""

from __future__ import annotations

import ast
import importlib.util
from datetime import datetime, timezone
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

_SCRIPT_DIR = Path(__file__).resolve().parents[3] / "digiquant" / "scripts" / "atlas"


def _load_script(name: str) -> ModuleType:
    path = _SCRIPT_DIR / f"{name}.py"
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.mark.parametrize(
    ("script_name", "children"),
    [
        (
            "backfill_position_events",
            ["execute_at_open.py", "backfill_execution_prices.py"],
        ),
        (
            "ensure_position_activity_through_today",
            [
                "refresh_performance_metrics.py",
                "backfill_position_events.py",
                "reconcile_position_events_from_positions.py",
            ],
        ),
    ],
)
def test_activity_wrappers_resolve_existing_sibling_scripts(
    script_name: str, children: list[str]
) -> None:
    module = _load_script(script_name)

    script_dir = module._script_dir()

    assert script_dir == _SCRIPT_DIR
    assert all((script_dir / child).is_file() for child in children)


@pytest.mark.parametrize(
    ("now_utc", "schedule", "expected"),
    [
        ("2026-08-05T13:20:00+00:00", "35 13 * * MON-FRI", False),
        ("2026-08-05T13:35:00+00:00", "35 13 * * MON-FRI", True),
        ("2026-08-05T15:41:00+00:00", "35 13 * * MON-FRI", True),
        ("2026-08-05T15:41:00+00:00", "35 14 * * MON-FRI", False),
        ("2026-01-05T14:35:00+00:00", "35 14 * * MON-FRI", True),
        ("2026-01-05T15:35:00+00:00", "35 13 * * MON-FRI", False),
    ],
)
def test_market_open_gate_selects_the_seasonal_cron_and_allows_delay(
    now_utc: str, schedule: str, expected: bool
) -> None:
    module = _load_script("market_open_gate")

    actual = module.should_run_at_open(
        now=datetime.fromisoformat(now_utc).astimezone(timezone.utc),
        schedule=schedule,
    )

    assert actual is expected


def test_market_open_gate_allows_manual_dispatch() -> None:
    module = _load_script("market_open_gate")

    assert module.should_run_at_open(
        now=datetime.fromisoformat("2026-08-05T12:00:00+00:00"),
        schedule="",
        force=True,
    )


def test_market_open_gate_treats_naive_replay_timestamp_as_utc() -> None:
    module = _load_script("market_open_gate")

    assert module.parse_utc("2026-08-05T13:35:00") == datetime(
        2026, 8, 5, 13, 35, tzinfo=timezone.utc
    )


def test_backfill_requires_the_ledger_like_the_cron_does() -> None:
    """Every `execute_at_open.py` subprocess in the backfill carries `--require-ledger` (#2589).

    Matches `pipeline-digiquant-prices.yml`: opening-snapshot seed + cold-start decline keep
    empty lots from inventing OPEN/EXIT; requiring the ledger prevents a silent prose
    fallback. Asserted over the AST rather than source text.
    """
    source = (_SCRIPT_DIR / "backfill_position_events.py").read_text()
    tree = ast.parse(source)

    call_sites: list[list[str]] = []
    opaque: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if not (isinstance(func, ast.Attribute) and func.attr == "run"):
            continue
        # argv can arrive positionally or as `args=`; read whichever this call site used, so the
        # keyword form is not a way past the classification below.
        argv: ast.expr | None = node.args[0] if node.args else None
        if argv is None:
            argv = next((kw.value for kw in node.keywords if kw.arg == "args"), None)
        if isinstance(argv, ast.List):
            call_sites.append([ast.unparse(element) for element in argv.elts])
        else:
            opaque.append(ast.unparse(node))

    # A hoisted argv (`cmd = [...]; subprocess.run(cmd)`) carries no flags this walk can read.
    # Skipping it would leave the literal-invocation count below still satisfied while a third
    # door onto execute_at_open.py stood open with no flag on it, so it fails here instead.
    assert not opaque, (
        f"subprocess call site(s) with a non-literal argv: {opaque}; a hoisted argv hides its "
        "flags from this test — inline the list, or teach the test to follow the variable"
    )

    # Classify every call site rather than filtering for the ones we expect. A third door onto
    # `execute_at_open.py` opened under a different variable name would satisfy a substring
    # filter's count while carrying no flag; here it fails as unclassified instead.
    invocations = [argv for argv in call_sites if any("exe_script" in el for el in argv)]
    price_runs = [argv for argv in call_sites if any("price_script" in el for el in argv)]
    unclassified = [
        argv for argv in call_sites if argv not in invocations and argv not in price_runs
    ]

    assert not unclassified, (
        f"unclassified subprocess call site(s): {unclassified}; if this invokes execute_at_open.py "
        "it must carry --require-ledger, and this test must be taught to see it"
    )
    assert len(invocations) == 2, (
        f"expected 2 literal-argv execute_at_open invocations, found {len(invocations)}; "
        "a call site was added, removed, or hoisted out of a literal list"
    )
    for argv in invocations:
        assert "'--require-ledger'" in argv, f"invocation missing --require-ledger: {argv}"
        assert "'--no-ledger'" not in argv, f"invocation must not defer with --no-ledger: {argv}"

    # The dry-run branch prints the command instead of running it, so it escapes the walk above.
    # An operator reads that line to decide whether the real run is safe; if it drifts from the
    # command actually issued, the dry run is worse than no output at all.
    previews = [
        ast.unparse(node.args[0])
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id == "print"
        and node.args
        and "exe_script" in ast.unparse(node.args[0])
    ]

    assert len(previews) == 2, (
        f"expected 2 dry-run previews of execute_at_open, found {len(previews)}"
    )
    for preview in previews:
        assert "--require-ledger" in preview, f"dry-run preview missing --require-ledger: {preview}"
        assert "--no-ledger" not in preview, f"dry-run preview must not defer: {preview}"
