"""REM-012: execute_python subprocess sandbox and escape refusal."""

from __future__ import annotations

import os

import polars as pl
import pytest


@pytest.mark.unit
def test_execute_python_disabled_by_default(monkeypatch):
    monkeypatch.delenv("DIGI_ALLOW_CODE_EXEC", raising=False)
    from digigraph.tools.analytics.execute_python import execute_python_on_datasets

    out = execute_python_on_datasets(
        dataset_paths=["x"],
        session_id="s",
        output_name="out",
        code="result = df_0",
    )
    assert out.get("error")
    assert "disabled" in out["error"].lower()


@pytest.mark.unit
def test_validate_user_code_rejects_os_import():
    from digigraph.tools.analytics.execute_python_sandbox import (
        UserCodeRejected,
        validate_user_code,
    )

    with pytest.raises(UserCodeRejected):
        validate_user_code("import os\nresult = df_0")


@pytest.mark.unit
def test_run_in_subprocess_rejects_open(monkeypatch):
    monkeypatch.setenv("DIGI_ALLOW_CODE_EXEC", "1")
    from digigraph.tools.analytics.execute_python_sandbox import run_in_subprocess

    df = pl.DataFrame({"a": [1]})
    _, err = run_in_subprocess(
        code="open('/etc/passwd')\nresult = df_0",
        dataframes=[df],
        timeout_seconds=5,
    )
    assert err is not None


@pytest.mark.unit
def test_run_in_subprocess_success(monkeypatch):
    pytest.importorskip("digigraph.tools.analytics.execute_python_worker")
    monkeypatch.setenv("DIGI_ALLOW_CODE_EXEC", "1")
    from digigraph.tools.analytics.execute_python_sandbox import run_in_subprocess

    df = pl.DataFrame({"a": [1, 2]})
    out, err = run_in_subprocess(
        code="result = df_0.filter(pl.col('a') > 1)",
        dataframes=[df],
        timeout_seconds=10,
    )
    if err and "ModuleNotFoundError" in err:
        pytest.skip("digigraph package not installed editable for subprocess worker")
    assert err is None
    assert out is not None
    assert out.height == 1
