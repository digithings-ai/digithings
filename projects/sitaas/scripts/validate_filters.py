#!/usr/bin/env python3
"""Query the Sitaas DigiSearch index with a filter and validate format + application.

- Builds OData from structured filters and validates the formatted string.
- Queries the index with that filter and asserts every result's metadata matches.

Run from repo root with Sitaas .env loaded (or set AZURE_SEARCH_*, DIGISEARCH_INDEX_CONFIG).

  cd /path/to/digi && make -C projects/sitaas probe   # loads .env
  python projects/sitaas/scripts/validate_filters.py
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv(env_path: Path) -> None:
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k, v = k.strip(), v.strip().strip("'\"")
            if k:
                os.environ[k] = v


def _ensure_index_config() -> None:
    p = os.environ.get("DIGISEARCH_INDEX_CONFIG")
    if p and Path(p).is_absolute() and Path(p).exists():
        return
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sitaas_index = repo_root / "projects" / "sitaas" / "indexes" / "unified-content-index.yaml"
    if sitaas_index.exists():
        os.environ["DIGISEARCH_INDEX_CONFIG"] = str(sitaas_index)
    elif p:
        resolved = (Path.cwd() / p).resolve()
        if resolved.exists():
            os.environ["DIGISEARCH_INDEX_CONFIG"] = str(resolved)


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sitaas_env = repo_root / "projects" / "sitaas" / ".env"
    if sitaas_env.exists():
        _load_dotenv(sitaas_env)
    _ensure_index_config()

    try:
        from digisearch.indexes.backends.azure_search import (
            _build_odata_filter,
            _get_index_config,
            is_azure_configured,
            query_azure,
        )
        from digisearch.core.models import DigiQuery
    except ImportError as e:
        print("DigiSearch Azure backend not available:", e, file=sys.stderr)
        return 1

    if not is_azure_configured():
        print("Azure not configured. Set AZURE_SEARCH_* and DIGISEARCH_INDEX_CONFIG.", file=sys.stderr)
        return 1

    cfg = _get_index_config()
    filterable = cfg.get("filterable_fields") or []
    index_name = cfg.get("index_name", "")

    # 1) Validate OData format for structured filters
    structured = [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}]
    odata = _build_odata_filter(structured, filterable)
    expected = "(sourceType eq 'EXCHANGE')"
    if odata != expected:
        print(f"FILTER FORMAT: FAIL – expected {expected!r}, got {odata!r}", file=sys.stderr)
        return 1
    print("FILTER FORMAT: OK – OData built as", repr(odata))

    # 2) Query with filter
    q = DigiQuery(
        text="*",
        top_k=20,
        mode="simple",
        filters={"structured": structured},
    )
    results = query_azure(q, index_name=None)
    print(f"Query (index={index_name}, filter=sourceType eq EXCHANGE): {len(results)} results")

    # 3) Validate every result has metadata matching the filter
    failed = []
    for i, r in enumerate(results):
        meta = r.chunk.metadata or {}
        st = meta.get("sourceType")
        if st != "EXCHANGE":
            failed.append((i + 1, st))
    if failed:
        print("FILTER APPLIED: FAIL – result metadata did not match filter:", failed[:5], file=sys.stderr)
        return 1
    print("FILTER APPLIED: OK – all results have sourceType=EXCHANGE")
    return 0


if __name__ == "__main__":
    sys.exit(main())
