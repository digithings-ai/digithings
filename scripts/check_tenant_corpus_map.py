"""Drift gate: tenant corpus map must agree across its three blobs (refs #3854).

Compares key sets AND per-key ``digisearchIndex``/``vaultPathPrefix`` values across:
(a) ``infra/digichat-release/compose.profile-a-bundle.override.yml``
``DIGICHAT_EMBED_TENANTS`` JSON (only entries carrying a ``backend`` with
``digisearchIndex`` — the ``digithings.ai`` + ``occ.digithings.ai`` hosts),
(b) ``cloudflare/digithings-stack-cloudflare/wrangler.toml`` ``DIGI_TENANT_CORPUS_MAP``,
(c) ``cloudflare/digithings-stack-cloudflare/src/index.ts`` fallback literal
(``DIGI_TENANT_CORPUS_MAP: env... ?? '<json>'``).

Exit 0 when all three agree, 1 with a unified diff on drift. This deliberately
does NOT unify the blobs — it only refuses silent drift between them.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import tomllib
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

_COMPOSE_REL = Path("infra/digichat-release/compose.profile-a-bundle.override.yml")
_WRANGLER_REL = Path("cloudflare/digithings-stack-cloudflare/wrangler.toml")
_INDEX_TS_REL = Path("cloudflare/digithings-stack-cloudflare/src/index.ts")

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"
_FALLBACK_RE = re.compile(
    r"DIGI_TENANT_CORPUS_MAP:\s*env\.DIGI_TENANT_CORPUS_MAP\s*\?\?\s*'((?:[^'\\]|\\.)*)'",
)

#: The only corpus keys compared — sibling keys (research prompts, tokens) are out of scope.
_FIELDS = ("digisearchIndex", "vaultPathPrefix")


def default_compose_file() -> Path:
    return REPO_ROOT / _COMPOSE_REL


def default_wrangler_file() -> Path:
    return REPO_ROOT / _WRANGLER_REL


def default_index_ts_file() -> Path:
    return REPO_ROOT / _INDEX_TS_REL


def extract_embed_corpus(tenants: dict[str, Any]) -> dict[str, dict[str, str]]:
    """Reduce ``DIGICHAT_EMBED_TENANTS`` to ``{slug: corpus}``, skipping entries
    without a ``backend`` carrying ``digisearchIndex``."""
    out: dict[str, dict[str, str]] = {}
    for _host, entry in tenants.items():
        if not isinstance(entry, dict):
            continue
        backend = entry.get("backend")
        if not isinstance(backend, dict) or not backend.get("digisearchIndex"):
            continue
        slug = entry.get("slug")
        if not isinstance(slug, str) or not slug.strip():
            continue
        out[slug.strip()] = {field: str(backend.get(field, "")) for field in _FIELDS}
    return out


def _reduce_corpus_map(data: Any) -> dict[str, dict[str, str]]:
    """Reduce a parsed ``DIGI_TENANT_CORPUS_MAP`` object to the compared fields."""
    if not isinstance(data, dict):
        raise ValueError(f"{_ENV_VAR} must be a JSON object keyed by tenant slug")
    return {
        str(slug): {field: str(value.get(field, "")) for field in _FIELDS}
        for slug, value in data.items()
        if isinstance(value, dict)
    }


def load_embed_map(compose_path: Path) -> dict[str, dict[str, str]]:
    doc = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8"))
    raw = doc["services"]["digichat"]["environment"]["DIGICHAT_EMBED_TENANTS"]
    tenants = json.loads(raw)
    if not isinstance(tenants, dict):
        raise ValueError("DIGICHAT_EMBED_TENANTS must be a JSON object keyed by host")
    return extract_embed_corpus(tenants)


def load_wrangler_map(wrangler_path: Path) -> dict[str, dict[str, str]]:
    with open(wrangler_path, "rb") as fh:
        doc = tomllib.load(fh)
    raw: Any = doc.get(_ENV_VAR, doc.get("vars", {}).get(_ENV_VAR))
    if not isinstance(raw, str) or not raw.strip():
        raise ValueError(f"{_ENV_VAR} missing from {wrangler_path}")
    return _reduce_corpus_map(json.loads(raw))


def load_index_ts_map(index_ts_path: Path) -> dict[str, dict[str, str]]:
    src = Path(index_ts_path).read_text(encoding="utf-8")
    match = _FALLBACK_RE.search(src)
    if not match:
        raise ValueError(f"{_ENV_VAR} fallback literal not found in {index_ts_path}")
    return _reduce_corpus_map(json.loads(match.group(1)))


def _canonical(source_map: dict[str, dict[str, str]]) -> list[str]:
    return json.dumps(source_map, indent=2, sort_keys=True).splitlines()


def compare_maps(named: list[tuple[str, dict[str, dict[str, str]]]]) -> dict[str, Any]:
    """Compare key sets and per-key values across named sources.

    Returns ``{"ok": bool, "problems": [...], "diff": str}`` — ``diff`` is a
    unified diff of the canonical forms, empty when everything agrees.
    """
    problems: list[str] = []
    diffs: list[str] = []
    base_name, base = named[0]
    for name, other in named[1:]:
        missing = sorted(set(base) - set(other))
        extra = sorted(set(other) - set(base))
        if missing:
            problems.append(f"{name} drops key(s) present in {base_name}: {missing}")
        if extra:
            problems.append(f"{name} adds key(s) absent from {base_name}: {extra}")
        for slug in sorted(set(base) & set(other)):
            for field in _FIELDS:
                if base[slug].get(field) != other[slug].get(field):
                    problems.append(
                        f"{name}[{slug}].{field}: {other[slug].get(field)!r} "
                        f"!= {base_name} {base[slug].get(field)!r}"
                    )
        if base != other:
            diffs.extend(
                difflib.unified_diff(
                    _canonical(base),
                    _canonical(other),
                    fromfile=base_name,
                    tofile=name,
                    lineterm="",
                )
            )
    return {"ok": not problems, "problems": problems, "diff": "\n".join(diffs)}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--compose-file", type=Path, default=default_compose_file())
    parser.add_argument("--wrangler-file", type=Path, default=default_wrangler_file())
    parser.add_argument("--index-ts-file", type=Path, default=default_index_ts_file())
    args = parser.parse_args(argv)

    named = [
        ("embed", load_embed_map(args.compose_file)),
        ("wrangler", load_wrangler_map(args.wrangler_file)),
        ("index.ts", load_index_ts_map(args.index_ts_file)),
    ]
    report = compare_maps(named)
    if report["ok"]:
        print(f"corpus map ok: {len(named[0][1])} tenant(s) agree across 3 blobs")
        return 0
    print("corpus map DRIFT:")
    for problem in report["problems"]:
        print(f"  {problem}")
    print(report["diff"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
