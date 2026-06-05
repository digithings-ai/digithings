"""Subprocess sandbox helpers for user Python execution (REM-012)."""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import polars as pl

_FORBIDDEN = re.compile(
    r"(?i)"
    r"(\bimport\s+(os|sys|subprocess|socket|pathlib|shutil|builtins|ctypes)\b"
    r"|__import__\s*\("
    r"|\bopen\s*\("
    r"|\bexec\s*\("
    r"|\beval\s*\("
    r"|\bcompile\s*\("
    r"|\bgetattr\s*\(\s*__"
    r"|\b__\w+__\s*\.?\s*__)"
)


class UserCodeRejected(ValueError):
    """User code failed static safety checks."""


def validate_user_code(code: str) -> None:
    if not code or not code.strip():
        raise UserCodeRejected("code is required")
    if _FORBIDDEN.search(code):
        raise UserCodeRejected("Code contains disallowed constructs (imports, open, exec, etc.)")


def run_in_subprocess(
    *,
    code: str,
    dataframes: list[pl.DataFrame],
    timeout_seconds: int,
) -> tuple[pl.DataFrame | None, str | None]:
    """Execute user code in a child process; return (dataframe, error_message)."""
    try:
        validate_user_code(code)
    except UserCodeRejected as e:
        return None, str(e)
    with tempfile.TemporaryDirectory(prefix="digi-exec-") as td:
        td_path = Path(td)
        dataset_paths: list[str] = []
        for i, df in enumerate(dataframes):
            p = td_path / f"df_{i}.parquet"
            df.write_parquet(p)
            dataset_paths.append(str(p))
        out_parquet = td_path / "result.parquet"
        payload = {
            "code": code,
            "dataset_paths": dataset_paths,
            "output_parquet": str(out_parquet),
        }
        env = os.environ.copy()
        env["PYTHONNOUSERSITE"] = "1"
        env["HOME"] = td
        src_root = Path(__file__).resolve().parents[3]
        env["PYTHONPATH"] = os.pathsep.join([str(src_root), env.get("PYTHONPATH", "")]).strip(
            os.pathsep
        )
        try:
            proc = subprocess.run(
                [sys.executable, "-m", "digigraph.tools.analytics.execute_python_worker"],
                input=json.dumps(payload),
                capture_output=True,
                text=True,
                timeout=max(timeout_seconds, 1) + 5,
                env=env,
            )
        except subprocess.TimeoutExpired:
            return None, "Execution timed out"
        if proc.returncode != 0 and not proc.stdout.strip():
            err = (proc.stderr or "").strip() or "subprocess failed"
            return None, err
        try:
            body = json.loads(proc.stdout or "{}")
        except json.JSONDecodeError:
            return None, "invalid worker response"
        if body.get("error"):
            return None, str(body["error"])
        if not out_parquet.is_file():
            return None, "worker did not produce output"
        return pl.read_parquet(out_parquet), None
