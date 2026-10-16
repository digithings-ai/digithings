"""Apply gitignored vendor env files onto core Edge Function secrets.

Default is ``--check`` (names only). ``--apply`` runs ``supabase secrets set``
then redeploys billing/settings functions. Never prints secret values.
"""

from __future__ import annotations

import argparse
import subprocess
import tempfile
from collections.abc import Callable, Sequence
from pathlib import Path

from digiquant.execution.vendor_secret_files import (
    BILLING_FUNCTIONS,
    EXIT_VENDOR_FILES_OR_KEYS_MISSING,
    apply_ready,
    format_vendor_apply_blocked,
    function_deploy_argv,
    inspect_vendor_secret_files,
    load_vendor_secret_environ,
    secrets_set_argv,
    vendor_secrets_dir,
    write_vendor_secret_env_file,
)

EXIT_APPLY_FAILED: int = 3
RunArgv = Callable[[Sequence[str]], None]


def _run_argv(argv: Sequence[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def run_vendor_secret_apply(
    *,
    repo_root: Path,
    apply: bool,
    log: Callable[[str], None],
    run: RunArgv = _run_argv,
) -> int:
    report = inspect_vendor_secret_files(repo_root)
    if report.present_files:
        log("vendor files present: " + ", ".join(report.present_files))
    if report.present_key_names:
        log("vendor key names present: " + ", ".join(report.present_key_names))
    if not apply_ready(report):
        log(format_vendor_apply_blocked(report))
        return EXIT_VENDOR_FILES_OR_KEYS_MISSING
    if not apply:
        log("vendor secret apply: check ok (all required files and keys present)")
        return 0
    environ = load_vendor_secret_environ(repo_root)
    log("vendor secret apply: setting core EF secret names (values not logged)")
    env_file: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            dir=vendor_secrets_dir(repo_root),
            prefix=".vendor-secret-apply-",
            suffix=".env",
            delete=False,
        ) as handle:
            env_file = Path(handle.name)
        write_vendor_secret_env_file(environ, env_file)
        run(secrets_set_argv(env_file))
        for function in BILLING_FUNCTIONS:
            log(f"vendor secret apply: deploy {function}")
            run(function_deploy_argv(function))
    except (OSError, subprocess.CalledProcessError):
        log("vendor secret apply failed (supabase output not echoed)")
        return EXIT_APPLY_FAILED
    finally:
        if env_file is not None:
            env_file.unlink(missing_ok=True)
    log("vendor secret apply: done")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Push secrets and redeploy billing/settings functions (default: check only)",
    )
    parser.add_argument(
        "--repo-root",
        type=Path,
        default=Path.cwd(),
        help="Repository root (contains .local/secrets/)",
    )
    args = parser.parse_args(argv)
    return run_vendor_secret_apply(
        repo_root=args.repo_root,
        apply=args.apply,
        log=lambda msg: print(msg, flush=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
