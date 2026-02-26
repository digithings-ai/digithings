#!/usr/bin/env python3
"""Fetch a few records from the unified-content index and print full structure (including JSON fields).

Use output to document unified-content-index.yaml (schema, JSON/complex fields, filtering).

Run from repo root with Sitaas .env loaded:
  python projects/sitaas/scripts/inspect_index_structure.py
"""

from __future__ import annotations

import json
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


def _describe_value(v, depth: int = 0, max_str: int = 80) -> str:
    """Describe type and structure for docs (scalar sample, dict keys, list length)."""
    indent = "  " * depth
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return str(v)
    if isinstance(v, str):
        s = v.replace("\n", " ").strip()
        return repr(s[:max_str] + "..." if len(s) > max_str else s)
    if isinstance(v, list):
        if not v:
            return "[]"
        head = _describe_value(v[0], depth + 1, max_str)
        return f"[ {head} ... ] (len={len(v)})"
    if isinstance(v, dict):
        keys = list(v.keys())[:15]
        kstr = ", ".join(keys)
        if len(v) > 15:
            kstr += f", ... ({len(v)} keys)"
        return f"{{ {kstr} }}"
    return type(v).__name__


def main() -> int:
    repo_root = Path(__file__).resolve().parent.parent.parent.parent
    sitaas_env = repo_root / "projects" / "sitaas" / ".env"
    if sitaas_env.exists():
        _load_dotenv(sitaas_env)
    _ensure_index_config()

    try:
        from digisearch.indexes.backends.azure_search import is_azure_configured, query_azure, _get_index_config
        from digisearch.core.models import DigiQuery
    except ImportError as e:
        print("DigiSearch Azure backend not available:", e, file=sys.stderr)
        return 1

    if not is_azure_configured():
        print("Azure not configured.", file=sys.stderr)
        return 1

    cfg = _get_index_config()
    # Request all result_metadata_fields so we get JSON fields in response
    q = DigiQuery(text="*", top_k=5, mode="simple", columns=None)  # use default extra fields
    response = query_azure(q, index_name=None)
    results = response.results
    if not results:
        q2 = DigiQuery(text="the", top_k=5, mode="simple")
        response = query_azure(q2, index_name=None)
        results = response.results
    if not results:
        print("No results from index.", file=sys.stderr)
        return 1

    print("=== Index structure from", len(results), "sample record(s) ===\n")
    # Merge all keys from all results
    all_keys = set()
    for r in results:
        all_keys.update((r.chunk.metadata or {}).keys())
    for key in sorted(all_keys):
        if key.startswith("@"):
            continue
        # Collect types and sample from all results
        types_seen = set()
        samples = []
        complex_structure = None
        for r in results:
            meta = r.chunk.metadata or {}
            v = meta.get(key)
            if v is None:
                types_seen.add("null")
                continue
            types_seen.add(type(v).__name__)
            desc = _describe_value(v)
            if isinstance(v, (dict, list)) and desc not in [s for s in samples]:
                complex_structure = v
            if len(samples) < 2 and (isinstance(v, (str, int, float, bool)) or (isinstance(v, (list, dict)) and not complex_structure)):
                samples.append(desc)

        type_str = ", ".join(sorted(types_seen))
        sample_str = " | ".join(samples[:2]) if samples else "-"
        print(f"  {key}: type={type_str}  sample={sample_str}")
        if complex_structure is not None:
            try:
                out = json.dumps(complex_structure, indent=2, default=str)[:1200]
                print(f"    structure:\n{out}\n    ..." if len(out) >= 1200 else f"    structure:\n{out}")
            except Exception:
                print(f"    structure: (non-JSON-serializable) {_describe_value(complex_structure)}")
        print()

    # Dump one full record (truncate body) for reference
    print("\n=== One full record (body truncated) ===")
    meta = dict(results[0].chunk.metadata or {})
    meta.pop("@search.score", None)
    meta.pop("@search.reranker_score", None)
    if "body" in meta and isinstance(meta["body"], str) and len(meta["body"]) > 500:
        meta["body"] = meta["body"][:500] + "... [truncated]"
    print(json.dumps(meta, indent=2, default=str))

    return 0


if __name__ == "__main__":
    sys.exit(main())
