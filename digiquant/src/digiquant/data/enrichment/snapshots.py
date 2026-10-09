"""Gloomberb enrichment snapshot store (research staging, #4804).

Snapshots are enrichment-only by construction: each file wraps one
dispatcher JSON payload with provenance (tool, params, fetched_at, source,
delay notice, attribution). Nothing here is a source of record — pipeline
inputs stay on the R2/Supabase path.
"""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

SNAPSHOT_VERSION = 1
DEFAULT_KEEP_PER_TOOL = 30


def snapshot_root() -> Path:
    """Root dir, overridable via DIGIQUANT_ENRICHMENT_DIR (tests)."""
    override = (os.environ.get("DIGIQUANT_ENRICHMENT_DIR") or "").strip()
    if override:
        return Path(override)
    return Path("digiquant") / "data" / "enrichment" / "snapshots"


def _params_hash(params: dict) -> str:
    canonical = json.dumps(params, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()[:12]


def write_snapshot(tool: str, params: dict, payload_json: str, *, fetched_at: str) -> Path:
    """Persist one dispatcher payload. Returns the page path; refreshes latest.json."""
    from digiquant.data.gloomberb.attribution import (
        GLOOMBERB_ATTRIBUTION,
        GLOOMBERB_DELAY_NOTICE,
    )

    tool_dir = snapshot_root() / tool
    tool_dir.mkdir(parents=True, exist_ok=True)
    doc = {
        "snapshot_version": SNAPSHOT_VERSION,
        "tool": tool,
        "params": params,
        "fetched_at": fetched_at,
        "source": "gloomberb",
        "delay_notice": GLOOMBERB_DELAY_NOTICE,
        "attribution": GLOOMBERB_ATTRIBUTION,
        "payload": payload_json,
    }
    day = fetched_at[:10]
    page = tool_dir / f"{day}__{_params_hash(params)}.json"
    page.write_text(json.dumps(doc, indent=2), encoding="utf-8")
    (tool_dir / "latest.json").write_text(json.dumps(doc, indent=2), encoding="utf-8")
    return page


def load_latest(tool: str) -> str | None:
    """Newest snapshot path for ``tool`` (latest.json pointer), or None."""
    pointer = snapshot_root() / tool / "latest.json"
    return str(pointer) if pointer.is_file() else None


def prune_tool(tool: str, *, keep: int = DEFAULT_KEEP_PER_TOOL) -> int:
    """Delete oldest dated pages beyond ``keep`` (latest.json never pruned). Returns removed count."""
    tool_dir = snapshot_root() / tool
    pages = sorted(
        p for p in tool_dir.glob("[0-9]*__*.json") if not p.name.endswith(".metrics.json")
    )
    doomed = pages[: max(len(pages) - keep, 0)]
    for path in doomed:
        path.unlink()
        companion = path.parent / f"{path.stem}.metrics.json"
        if companion.is_file():
            companion.unlink()
    return len(doomed)


def merge_series_page(
    history: list[dict], page: list[dict], *, date_key: str = "date"
) -> list[dict]:
    """Newest-page merge for capped series (econ_series limit<=1000, no offset).

    Appends observations strictly newer than history's max date; drops
    duplicates by date (page wins on re-statement); never deletes history
    (no full-replace with one page). Empty page raises.
    """
    if not page:
        raise ValueError("refusing to merge an empty page into series history")
    have = {row[date_key]: row for row in history}
    for row in page:
        have[row[date_key]] = row
    return [have[day] for day in sorted(have)]
