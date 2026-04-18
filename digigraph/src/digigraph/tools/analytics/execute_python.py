"""Sandboxed execution of Python (Polars) code on session datasets. Produces a new dataset_ref.

WARNING: exec() with restricted globals is NOT a real sandbox. This tool is disabled by default.
Set DIGI_ALLOW_CODE_EXEC=true to enable it (only in controlled environments).
"""

from __future__ import annotations

import logging
import signal
from typing import Any

from digigraph.policy import code_execution_allowed
from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.load import load_dataset

logger = logging.getLogger(__name__)


def execute_python_on_datasets(
    dataset_paths: list[str],
    session_id: str | None,
    output_name: str,
    code: str,
    timeout_seconds: int = 30,
) -> dict[str, Any]:
    """
    Run user code in a restricted environment. Datasets are loaded as df_0, df_1, ...
    Code must assign a Polars DataFrame to 'result' or have it as the last expression.
    Allowed: polars (pl), math, datetime. No file I/O, no network.

    Disabled by default. Set DIGI_ALLOW_CODE_EXEC=true to enable.
    """
    if not code_execution_allowed():
        logger.warning("execute_python_on_datasets called but DIGI_ALLOW_CODE_EXEC is not set — refusing")
        return {
            "error": "Code execution is disabled. Set DIGI_ALLOW_CODE_EXEC=true to enable (controlled environments only).",
            "dataset_ref": None,
            "rows": 0,
        }
    if not code or not code.strip():
        return {"error": "code is required", "dataset_ref": None, "rows": 0}
    if not dataset_paths:
        return {"error": "at least one dataset_ref is required", "dataset_ref": None, "rows": 0}

    dataframes: list[Any] = []
    for p in dataset_paths:
        try:
            df = load_dataset(p)
            dataframes.append(df)
        except Exception as e:
            return {"error": f"Failed to load dataset: {e}", "dataset_ref": None, "rows": 0}

    # Build restricted globals: only pl, math, datetime, and injected dfs
    import math
    import datetime
    import polars as pl

    restricted: dict[str, Any] = {
        "pl": pl,
        "math": math,
        "datetime": datetime,
        "result": None,
    }
    for i, df in enumerate(dataframes):
        restricted[f"df_{i}"] = df

    try:
        if hasattr(signal, "SIGALRM"):
            def timeout_handler(signum: int, frame: Any) -> None:
                raise TimeoutError("Execution timed out")
            signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(timeout_seconds)
        exec(compile(code.strip(), "<user_code>", "exec"), restricted)
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
    except TimeoutError as e:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        return {"error": str(e), "dataset_ref": None, "rows": 0}
    except Exception as e:
        if hasattr(signal, "SIGALRM"):
            signal.alarm(0)
        return {"error": f"Execution failed: {e}", "dataset_ref": None, "rows": 0}

    result = restricted.get("result")
    if result is None:
        # Try last assignment to a name that looks like a DataFrame
        for k, v in restricted.items():
            if k.startswith("df_") and hasattr(v, "to_dicts"):
                result = v
                break
    if result is None or not hasattr(result, "to_dicts"):
        return {"error": "Code must assign a Polars DataFrame to 'result'", "dataset_ref": None, "rows": 0}

    try:
        df_out = result if hasattr(result, "to_dicts") else result
        return write_result(df_out, session_id, output_name)
    except Exception as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
