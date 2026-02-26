#!/usr/bin/env python3
"""Probe the Sitaas DigiSearch Azure index: sample docs, distinct filter values, and filter test.

Run from repo root with Sitaas .env loaded, or from projects/sitaas with .env in cwd:

  # From repo root (load .env from project)
  cd /path/to/digi && DIGISEARCH_INDEX_CONFIG=projects/sitaas/indexes/unified-content-index.yaml \\
    python -m projects.sitaas.scripts.probe_index

  # From projects/sitaas (DIGISEARCH_INDEX_CONFIG=indexes/unified-content-index.yaml in .env)
  cd projects/sitaas && set -a && source .env && set +a && python scripts/probe_index.py

Requires: AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, and DIGISEARCH_INDEX_CONFIG pointing
at projects/sitaas/indexes/unified-content-index.yaml (or equivalent).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


def _load_dotenv(env_path: Path) -> None:
    """Set os.environ from .env file (KEY=value, skip comments and empty)."""
    if not env_path.exists():
        return
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            k = k.strip()
            v = v.strip().strip("'\"")
            if k:
                os.environ[k] = v


def _ensure_index_config() -> None:
    """Ensure DIGISEARCH_INDEX_CONFIG points at Sitaas index YAML (absolute path)."""
    p = os.environ.get("DIGISEARCH_INDEX_CONFIG")
    if p and Path(p).is_absolute() and Path(p).exists():
        return
    # Resolve relative to repo root or script's project root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sitaas_index = repo_root / "projects" / "sitaas" / "indexes" / "unified-content-index.yaml"
    if sitaas_index.exists():
        os.environ["DIGISEARCH_INDEX_CONFIG"] = str(sitaas_index)
    elif p:
        resolved = (Path.cwd() / p).resolve()
        if resolved.exists():
            os.environ["DIGISEARCH_INDEX_CONFIG"] = str(resolved)


def main() -> int:
    # Prefer .env from projects/sitaas when running from repo root
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sitaas_env = repo_root / "projects" / "sitaas" / ".env"
    if sitaas_env.exists():
        _load_dotenv(sitaas_env)
    _ensure_index_config()

    try:
        from digisearch.indexes.backends.azure_search import (
            is_azure_configured,
            query_azure,
            _get_index_config,
        )
        from digisearch.core.models import DigiQuery
    except ImportError as e:
        print("DigiSearch Azure backend not available:", e, file=sys.stderr)
        print("Install: pip install -e 'digisearch[azure]'", file=sys.stderr)
        return 1

    if not is_azure_configured():
        print("Azure not configured. Set AZURE_SEARCH_ENDPOINT, AZURE_SEARCH_API_KEY, and index config.", file=sys.stderr)
        return 1

    cfg = _get_index_config()
    index_name = cfg.get("index_name", "")
    filterable = cfg.get("filterable_fields") or []
    print("Index:", index_name)
    print("Filterable fields:", ", ".join(filterable))
    print()

    # 1) Sample query – what's in the index
    q = DigiQuery(text="*", top_k=20, mode="simple")
    results = query_azure(q, index_name=None)
    print(f"Sample query ('*', top_k=20): {len(results)} results")
    if not results:
        print("No documents returned. Index may be empty or query syntax may not support '*'.")
        # Try a simple word
        q2 = DigiQuery(text="the", top_k=20, mode="simple")
        results = query_azure(q2, index_name=None)
        print(f"Fallback query ('the', top_k=20): {len(results)} results")
    if results:
        # Distinct values for key filter fields
        from collections import defaultdict
        distinct: dict[str, set] = defaultdict(set)
        for r in results:
            for f in filterable:
                v = r.chunk.metadata.get(f)
                if v is not None:
                    distinct[f].add(str(v))
        print("\nDistinct values in sample (for filter validation):")
        for f in ["sourceType", "itemType", "fromAddress", "hasAttachments", "importance"]:
            if f in distinct and distinct[f]:
                vals = sorted(distinct[f])[:15]
                print(f"  {f}: {vals}")
        print("\nFirst result metadata keys:", list(results[0].chunk.metadata.keys())[:20])
        print("First result content preview:", (results[0].chunk.content or "")[:200])
    print()

    # 2) Structured filter test
    print("Structured filter test: sourceType eq 'EXCHANGE'")
    qf = DigiQuery(
        text="*",
        top_k=10,
        mode="simple",
        filters={"structured": [{"field": "sourceType", "op": "eq", "value": "EXCHANGE"}]},
    )
    filtered = query_azure(qf, index_name=None)
    print(f"  Results: {len(filtered)}")
    for r in filtered[:3]:
        st = r.chunk.metadata.get("sourceType", "")
        print(f"    sourceType={st!r} score={r.score}")
    print()

    # 3) Optional: second filter (hasAttachments)
    print("Structured filter test: sourceType eq 'EXCHANGE' and hasAttachments eq true")
    qf2 = DigiQuery(
        text="*",
        top_k=10,
        mode="simple",
        filters={
            "structured": [
                {"field": "sourceType", "op": "eq", "value": "EXCHANGE"},
                {"field": "hasAttachments", "op": "eq", "value": True},
            ],
        },
    )
    filtered2 = query_azure(qf2, index_name=None)
    print(f"  Results: {len(filtered2)}")
    for r in filtered2[:3]:
        st = r.chunk.metadata.get("sourceType", "")
        ha = r.chunk.metadata.get("hasAttachments", "")
        print(f"    sourceType={st!r} hasAttachments={ha} score={r.score}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
