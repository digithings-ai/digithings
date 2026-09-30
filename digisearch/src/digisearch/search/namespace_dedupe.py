"""Collapse cross-namespace twin hits in one result list.

Background (#4823): a serving index can hold the same vault content under
two path namespaces — live paths plus tenant-prefixed copies such as
``clients/digithings/...``. Vector IDs are path-derived
(``sha1(vault_path)``), so a re-sync under a new prefix *adds* copies
instead of overwriting, and the old vectors are never pruned. Both copies
then surface in a single ``/query`` response citing the same content twice.

This helper runs in ``run_query`` *before* normalization, the only layer
where full chunk bodies still exist (downstream carries 500-char snippets
at best). Entries are plain ``{"path", "content", "url"}`` dicts extracted
from backend ``Result`` objects. A collapse requires BOTH of:

* identical non-empty ``content`` (exact full-body equality), and
* paths suffix-related at a ``/`` boundary (``a/b.md`` vs ``x/a/b.md``).

The surviving copy keeps the earliest group position. Within a group the
http(s)-URL carrier wins when exactly one side has it (preserves the only
citable link); otherwise the longest — i.e. tenant-prefixed, vault-readable
under the #2265 tenant boundary — path wins.
"""

from __future__ import annotations

from typing import Any


def _is_http_url(value: Any) -> bool:
    return isinstance(value, str) and value.startswith(("http://", "https://"))


def _norm_path(value: Any) -> str:
    return value.strip().strip("/") if isinstance(value, str) else ""


def _suffix_related(left: str, right: str) -> bool:
    """True when both non-empty and one is a path-suffix of the other."""
    if not left or not right or left == right:
        return left == right and bool(left)
    longer, shorter = (left, right) if len(left) > len(right) else (right, left)
    return longer.endswith("/" + shorter)


def _carrier_url(entry: dict[str, Any]) -> bool:
    return _is_http_url(entry.get("url")) or _is_http_url(entry.get("path"))


def _better(winner: dict[str, Any], challenger: dict[str, Any]) -> bool:
    """True when *challenger* should replace *winner* within a twin group."""
    winner_url = _carrier_url(winner)
    challenger_url = _carrier_url(challenger)
    if challenger_url != winner_url:
        return challenger_url
    return len(_norm_path(challenger.get("path"))) > len(_norm_path(winner.get("path")))


def dedupe_namespace_copies(entries: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Return *entries* minus stale cross-namespace twins. Input not mutated."""
    groups: list[dict[str, Any]] = []  # {content, paths, winner, pos}
    for pos, entry in enumerate(entries):
        path = _norm_path(entry.get("path"))
        content = entry.get("content") or ""
        target = None
        if path and content:
            for group in groups:
                if group["content"] != content:
                    continue
                if any(_suffix_related(path, p) for p in group["paths"]):
                    target = group
                    break
        if target is None:
            groups.append({"content": content, "paths": [path], "winner": entry, "pos": pos})
        else:
            target["paths"].append(path)
            if _better(target["winner"], entry):
                target["winner"] = entry
    ordered = sorted(groups, key=lambda group: group["pos"])
    return [group["winner"] for group in ordered]
