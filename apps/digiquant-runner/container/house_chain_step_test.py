"""Argv and attempt-counter checks. Does not call uv or the chain."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import house_chain_step  # noqa: E402


def test_chain_argv_daily_flags() -> None:
    argv = house_chain_step.chain_argv(
        {
            "RUN_DATE": "2026-09-30",
            "REFRESH_SCOPE": "none",
            "GITHUB_RUN_ID": "run-1",
        }
    )
    assert argv == [
        "uv",
        "run",
        "--frozen",
        "--no-sync",
        "python",
        "-m",
        "digiquant.portfolio.chain",
        "--cadence",
        "daily",
        "--run-date",
        "2026-09-30",
        "--refresh-scope",
        "none",
    ]


def test_chain_argv_dry_run_and_resume() -> None:
    argv = house_chain_step.chain_argv(
        {
            "RUN_DATE": "2026-09-30",
            "REFRESH_SCOPE": "all",
            "DRY_RUN": "true",
            "RESUME_RUN_ID": "run-0",
        }
    )
    assert "--dry-run" in argv
    assert argv[argv.index("--resume-run-id") + 1] == "run-0"


def test_second_attempt_sets_digiquant_attempt() -> None:
    seen: list[str] = []

    def spawn(argv: list[str], env: dict[str, str]) -> int:
        del argv
        seen.append(env["DIGIQUANT_ATTEMPT"])
        return 1 if len(seen) == 1 else 0

    code = house_chain_step.run_attempts(
        {"RUN_DATE": "2026-09-30", "REFRESH_SCOPE": "none"},
        spawn,
        sleep=lambda _seconds: None,
    )
    assert code == 0
    assert seen == ["1", "2"]


def test_success_does_not_sleep_backoff() -> None:
    slept: list[float] = []

    def spawn(argv: list[str], env: dict[str, str]) -> int:
        del argv, env
        return 0

    code = house_chain_step.run_attempts(
        {"RUN_DATE": "2026-09-30", "REFRESH_SCOPE": "none"},
        spawn,
        sleep=slept.append,
    )
    assert code == 0
    assert slept == [0]


def test_wrapper_does_not_import_digiquant() -> None:
    source = Path(house_chain_step.__file__).read_text(encoding="utf-8")
    for line in source.splitlines():
        stripped = line.strip()
        if stripped.startswith("import digiquant") or stripped.startswith("from digiquant"):
            raise SystemExit(f"house_chain_step must not import digiquant: {stripped}")


def test_help_prints_caps() -> None:
    from io import StringIO
    from contextlib import redirect_stdout

    buf = StringIO()
    with redirect_stdout(buf):
        code = house_chain_step.main(["--help"])
    text = buf.getvalue()
    assert code == 0
    assert "MAX_OUTER_ATTEMPTS=2" in text
    assert "ATTEMPT_TIMEOUT_SECONDS=6000" in text
    assert "300" in text


def main() -> int:
    test_chain_argv_daily_flags()
    test_chain_argv_dry_run_and_resume()
    test_second_attempt_sets_digiquant_attempt()
    test_success_does_not_sleep_backoff()
    test_wrapper_does_not_import_digiquant()
    test_help_prints_caps()
    print("ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
