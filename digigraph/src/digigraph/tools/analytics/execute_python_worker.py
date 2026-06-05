"""Isolated subprocess worker for ``execute_python_on_datasets`` (REM-012).

Reads a JSON payload from stdin, runs user code with restricted globals, writes result parquet.
"""

from __future__ import annotations

import json
import math
import sys
from datetime import datetime
from pathlib import Path
from typing import Any  # noqa: ANN401 — restricted globals map for user code

import polars as pl

from digigraph.tools.analytics.execute_python_sandbox import (
    UserCodeRejected,
    validate_user_code,
)


def _run(payload: dict[str, Any]) -> dict[str, Any]:
    code = str(payload.get("code") or "")
    paths: list[str] = list(payload.get("dataset_paths") or [])
    output_path = str(payload.get("output_parquet") or "")
    validate_user_code(code)
    restricted: dict[str, Any] = {
        "pl": pl,
        "math": math,
        "datetime": datetime,
        "result": None,
    }
    for i, p in enumerate(paths):
        restricted[f"df_{i}"] = pl.read_parquet(p)
    exec(compile(code.strip(), "<user_code>", "exec"), restricted)
    result = restricted.get("result")
    if result is None:
        for k, v in restricted.items():
            if k.startswith("df_") and hasattr(v, "to_dicts"):
                result = v
                break
    if result is None or not hasattr(result, "to_dicts"):
        return {"error": "Code must assign a Polars DataFrame to 'result'"}
    out = result if isinstance(result, pl.DataFrame) else pl.DataFrame(result)
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    out.write_parquet(output_path)
    return {"ok": True, "rows": out.height, "columns": out.columns}


def main() -> None:
    try:
        payload = json.load(sys.stdin)
        print(json.dumps(_run(payload)))
    except UserCodeRejected as e:
        print(json.dumps({"error": str(e)}))
        sys.exit(1)
    except Exception as e:
        print(json.dumps({"error": f"Execution failed: {e}"}))
        sys.exit(1)


if __name__ == "__main__":
    main()
