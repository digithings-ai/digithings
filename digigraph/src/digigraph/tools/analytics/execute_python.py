"""Sandboxed execution of Python (Polars) code on session datasets. Produces a new dataset_ref.

When ``DIGI_ALLOW_CODE_EXEC`` is enabled, code runs in an isolated subprocess with a timeout.
Default is disabled (fail closed). In-process ``exec()`` is not used when execution is allowed.
"""

from __future__ import annotations

import logging
from typing import Any

from digigraph.policy import code_execution_allowed
from digigraph.tools.analytics.data_manipulation._helpers import write_result
from digigraph.tools.analytics.execute_python_sandbox import (
    UserCodeRejected,
    run_in_subprocess,
    validate_user_code,
)
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
    try:
        validate_user_code(code)
    except UserCodeRejected as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
    if not dataset_paths:
        return {"error": "at least one dataset_ref is required", "dataset_ref": None, "rows": 0}

    dataframes: list[Any] = []
    for p in dataset_paths:
        try:
            dataframes.append(load_dataset(p))
        except Exception as e:
            return {"error": f"Failed to load dataset: {e}", "dataset_ref": None, "rows": 0}

    try:
        result_df, err = run_in_subprocess(
            code=code,
            dataframes=dataframes,
            timeout_seconds=timeout_seconds,
        )
    except UserCodeRejected as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
    if err:
        return {"error": err, "dataset_ref": None, "rows": 0}
    if result_df is None:
        return {
            "error": "Code must assign a Polars DataFrame to 'result'",
            "dataset_ref": None,
            "rows": 0,
        }

    try:
        return write_result(result_df, session_id, output_name)
    except Exception as e:
        return {"error": str(e), "dataset_ref": None, "rows": 0}
