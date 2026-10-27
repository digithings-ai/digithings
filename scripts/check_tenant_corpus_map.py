"""Drift gate: the tenant corpus map must agree across its blobs (refs #3854).

Compares key sets AND per-key ``digisearchIndex``/``vaultPathPrefix`` values across:

(a) ``infra/digichat-release/compose.profile-a-bundle.override.yml``
``DIGICHAT_EMBED_TENANTS`` JSON (only entries carrying a ``backend`` with
``digisearchIndex`` — the ``digithings.ai`` + ``occ.digithings.ai`` hosts),
(b) ``apps/digithings-stack-cloudflare/wrangler.toml``, as a PAIR of vars:
``DIGI_TENANT_CORPUS_MAP`` + ``DIGI_TENANT_CORPUS_MAP_EXTRA``, joined with the
same precedence ``composeCorpusMap`` uses in ``src/index.ts`` — primary wins a
slug collision, so a stale extra half can never shadow the house entry.

Both sides then get the house-slug alias (``digithings`` and the live
``digithings-ai`` carry the same entry), because that is the map the container
receives. The alias rule is ``with_house_slug_alias`` here and
``withHouseSlugAlias`` in ``src/tenant-config.ts``; they must move together.

It also pins the third blob's ABSENCE. ``src/index.ts`` used to carry the whole
map as its ``??`` fallback literal, and that literal is why the deploy broke:
one Cloudflare text binding may not exceed 5.1 kB and the single value reached
5285 bytes, so ``wrangler deploy`` failed with code 10054 (2026-10-25). The
literal and ``_FALLBACK_RE``, the regex that read it, are retired together; what
replaces them is a check that neither a literal nor a dropped half has come
back. Prompt-level parity between the compose copy and the composed pair is
asserted instead in ``apps/digithings-stack-cloudflare/src/corpus-map-compose.test.js``,
which compares the two blobs as whole objects.

Exit 0 when the blobs agree, 1 with a unified diff on drift. This deliberately
does NOT unify the blobs — it only refuses silent drift between them.
"""

from __future__ import annotations

import argparse
import difflib
import json
import re
import tomllib
from pathlib import Path
from typing import Any  # score:allow untyped any — YAML config maps

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]

_COMPOSE_REL = Path("infra/digichat-release/compose.profile-a-bundle.override.yml")
_WRANGLER_REL = Path("apps/digithings-stack-cloudflare/wrangler.toml")
_INDEX_TS_REL = Path("apps/digithings-stack-cloudflare/src/index.ts")

_ENV_VAR = "DIGI_TENANT_CORPUS_MAP"
_EXTRA_ENV_VAR = "DIGI_TENANT_CORPUS_MAP_EXTRA"

#: The wiring ``src/index.ts`` must keep: both halves read, composed by name.
_WIRING_RE = re.compile(
    r"DIGI_TENANT_CORPUS_MAP:\s*composeCorpusMap\(\s*"
    r"env\.DIGI_TENANT_CORPUS_MAP,\s*"
    r"env\.DIGI_TENANT_CORPUS_MAP_EXTRA,?\s*\)"
)

#: A corpus map carried inline again would have to hold one of these.
_LITERAL_MARKERS = ("researchSystemPrompt", "digisearchIndex")

#: The only corpus keys compared — sibling keys (research prompts, tokens) are out of scope.
_FIELDS = ("digisearchIndex", "vaultPathPrefix")

#: The house slug the corpus map has always used, and the live embed slug.
#: `withHouseSlugAlias` in `src/tenant-config.ts` gives both the same entry, so
#: the gate has to model the alias too: comparing only the raw two-key blobs
#: would report agreement for a map the container never receives (DIG-5638).
HOUSE_TENANT_SLUG = "digithings"
LIVE_HOUSE_TENANT_SLUG = "digithings-ai"


def default_compose_file() -> Path:
    return REPO_ROOT / _COMPOSE_REL


def default_wrangler_file() -> Path:
    return REPO_ROOT / _WRANGLER_REL


def default_index_ts_file() -> Path:
    return REPO_ROOT / _INDEX_TS_REL


def _has_corpus(entry: dict[str, str] | None) -> bool:
    """True when an entry is a usable corpus, by the same rule the KV projection uses."""
    return isinstance(entry, dict) and bool(str(entry.get("digisearchIndex", "")).strip())


def with_house_slug_alias(mapping: dict[str, dict[str, str]]) -> dict[str, dict[str, str]]:
    """Apply the house-slug alias exactly as ``withHouseSlugAlias`` does in TS.

    `digithings` and `digithings-ai` carry the same corpus entry, so every arm of
    the runtime map agrees. The canonical `digithings` entry wins when it is
    usable; an empty entry never shadows a usable alias. A map with neither house
    slug is returned unchanged: an unknown tenant is never invented.
    """
    canonical = mapping.get(HOUSE_TENANT_SLUG)
    live = mapping.get(LIVE_HOUSE_TENANT_SLUG)
    if _has_corpus(canonical):
        house = canonical
    elif _has_corpus(live):
        house = live
    else:
        return mapping

    aliased: dict[str, dict[str, str]] = {}
    for slug, entry in mapping.items():
        if slug in (HOUSE_TENANT_SLUG, LIVE_HOUSE_TENANT_SLUG):
            continue
        aliased[slug] = entry
    aliased[HOUSE_TENANT_SLUG] = house
    aliased[LIVE_HOUSE_TENANT_SLUG] = house
    return aliased


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


def compose_corpus_vars(primary: str | None, extra: str | None) -> dict[str, Any]:
    """Join the split ``[vars]`` pair the way ``composeCorpusMap`` does in TS.

    Primary wins on a slug collision; an absent half contributes nothing. A half
    that is present but unparseable RAISES rather than degrading: ``composeCorpusMap``
    warns and ships the other half at runtime, but a drift gate that silently
    ignored half the map would report agreement it never checked.
    """
    merged: dict[str, Any] = {}
    for raw in (primary, extra):
        if not isinstance(raw, str) or not raw.strip():
            continue
        parsed = json.loads(raw)
        if not isinstance(parsed, dict):
            raise ValueError(f"a {_ENV_VAR} half is not a JSON object keyed by tenant slug")
        for slug, entry in parsed.items():
            merged.setdefault(slug, entry)
    return merged


def load_embed_map(compose_path: Path) -> dict[str, dict[str, str]]:
    doc = yaml.safe_load(Path(compose_path).read_text(encoding="utf-8"))
    raw = doc["services"]["digichat"]["environment"]["DIGICHAT_EMBED_TENANTS"]
    tenants = json.loads(raw)
    if not isinstance(tenants, dict):
        raise ValueError("DIGICHAT_EMBED_TENANTS must be a JSON object keyed by host")
    return with_house_slug_alias(extract_embed_corpus(tenants))


def load_wrangler_vars(wrangler_path: Path) -> tuple[str | None, str | None]:
    """``(primary, extra)`` raw values from wrangler ``[vars]``."""
    with open(wrangler_path, "rb") as fh:
        doc = tomllib.load(fh)
    variables = doc.get("vars", {})
    primary = variables.get(_ENV_VAR, doc.get(_ENV_VAR))
    extra = variables.get(_EXTRA_ENV_VAR, doc.get(_EXTRA_ENV_VAR))
    if not isinstance(primary, str) or not primary.strip():
        raise ValueError(f"{_ENV_VAR} missing from {wrangler_path}")
    return primary, extra if isinstance(extra, str) else None


def load_wrangler_map(wrangler_path: Path) -> dict[str, dict[str, str]]:
    primary, extra = load_wrangler_vars(wrangler_path)
    return with_house_slug_alias(_reduce_corpus_map(compose_corpus_vars(primary, extra)))


def check_index_ts_wiring(index_ts_path: Path) -> list[str]:
    """Problems with ``src/index.ts``'s side of the split, as human-readable strings.

    Two failure modes, both silent at runtime: a re-introduced corpus literal
    (which puts the binding back over the cap and re-forks the answers) and a
    wiring that stopped reading one half (which strips those tenants off the
    container without failing anything).
    """
    src = Path(index_ts_path).read_text(encoding="utf-8")
    problems: list[str] = []
    if not _WIRING_RE.search(src):
        problems.append(
            f"index.ts does not compose the [vars] pair: expected "
            f"`{_ENV_VAR}: composeCorpusMap(env.{_ENV_VAR}, env.{_EXTRA_ENV_VAR})`"
        )
    for marker in _LITERAL_MARKERS:
        if marker in src:
            problems.append(
                f"index.ts carries an inline corpus map (`{marker}`); the map belongs in "
                f"wrangler [vars], which is capped at 5.1 kB per binding"
            )
    return problems


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
    ]
    report = compare_maps(named)
    problems = list(report["problems"]) + check_index_ts_wiring(args.index_ts_file)
    if not problems:
        print(
            f"corpus map ok: {len(named[0][1])} slug(s) agree (house alias included) across "
            f"compose and the wrangler [vars] pair, and index.ts composes it"
        )
        return 0
    print("corpus map DRIFT:")
    for problem in problems:
        print(f"  {problem}")
    if report["diff"]:
        print(report["diff"])
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
