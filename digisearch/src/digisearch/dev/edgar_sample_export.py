"""Export Hugging Face EDGAR-CORPUS rows to markdown + YAML sidecars for DigiSearch /ingest.

Corpus: https://huggingface.co/datasets/eloukas/edgar-corpus (Loukas et al., ECONLP 2021).
SEC filings are public; use index name ``edgar_dev`` locally only.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Mapping

# 10-K Item labels aligned with dataset column names (stable ingest order).
SECTION_HEADERS: tuple[tuple[str, str], ...] = (
    ("section_1", "Item 1"),
    ("section_1A", "Item 1A — Risk Factors"),
    ("section_1B", "Item 1B"),
    ("section_2", "Item 2"),
    ("section_3", "Item 3"),
    ("section_4", "Item 4"),
    ("section_5", "Item 5"),
    ("section_6", "Item 6"),
    ("section_7", "Item 7 — MD&A"),
    ("section_7A", "Item 7A"),
    ("section_8", "Item 8"),
    ("section_9", "Item 9"),
    ("section_9A", "Item 9A"),
    ("section_9B", "Item 9B"),
    ("section_10", "Item 10"),
    ("section_11", "Item 11"),
    ("section_12", "Item 12"),
    ("section_13", "Item 13"),
    ("section_14", "Item 14"),
    ("section_15", "Item 15"),
)


def row_to_stem(row: Mapping[str, Any], index: int) -> str:
    """Build filesystem stem ``edgar_{cik}_{year}_{index}``."""
    cik = str(row.get("cik") or "unknown").strip()
    cik_safe = re.sub(r"[^\w-]", "", cik)[:16] or "unknown"
    year = row.get("year")
    y = int(year) if year is not None else 0
    return f"edgar_{cik_safe}_{y}_{index:05d}"


def row_to_markdown(row: Mapping[str, Any]) -> str:
    """Concatenate non-empty filing sections into one markdown document."""
    parts: list[str] = []
    fn = row.get("filename")
    if fn:
        parts.append(f"# SEC filing excerpt\n\n**Source file:** `{fn}`\n")
    for key, heading in SECTION_HEADERS:
        text = row.get(key)
        if text is None:
            continue
        s = str(text).strip()
        if not s:
            continue
        parts.append(f"\n## {heading}\n\n{s}\n")
    return "\n".join(parts).strip() + "\n" if parts else ""


def row_to_sidecar_metadata(row: Mapping[str, Any], stem: str) -> dict[str, Any]:
    """Metadata block for DigiSearch YAML sidecar (under ``metadata:``)."""
    fn = row.get("filename")
    title = str(fn).strip() if fn else stem
    year = row.get("year")
    pub_year = int(year) if year is not None else None
    cik = row.get("cik")
    source_url = None
    if cik is not None:
        source_url = f"https://www.sec.gov/cgi-bin/browse-edgar?action=getcompany&CIK={cik}&owner=exclude&count=40"

    meta: dict[str, Any] = {
        "title": title[:500],
        "evidence_tier": "industry",
        "peer_reviewed": False,
        "venue": "SEC EDGAR",
        "language": "en",
        "license_notes": (
            "SEC EDGAR public company filings; redistributed via EDGAR-CORPUS "
            "(Loukas et al., ECONLP 2021). Local dev/testing only."
        ),
    }
    if pub_year is not None:
        meta["publication_year"] = pub_year
    if source_url:
        meta["source_url"] = source_url
    if cik is not None:
        meta["asset_class_tags"] = ["edgar", "10k", f"cik_{cik}"]
    return meta


def sidecar_yaml_dict(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {"metadata": dict(metadata)}


def write_export_pair(
    out_dir: Path,
    stem: str,
    markdown: str,
    metadata: Mapping[str, Any],
) -> tuple[Path, Path]:
    """Write ``{stem}.md`` and ``{stem}.yaml``; return paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    md_path = out_dir / f"{stem}.md"
    yaml_path = out_dir / f"{stem}.yaml"
    md_path.write_text(markdown, encoding="utf-8")
    import yaml

    yaml_path.write_text(
        yaml.safe_dump(sidecar_yaml_dict(metadata), sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    return md_path, yaml_path


def clean_edgar_exports(out_dir: Path) -> int:
    """Remove ``edgar_*.md`` / ``edgar_*.yaml`` under *out_dir*. Returns file count removed."""
    if not out_dir.is_dir():
        return 0
    n = 0
    for p in out_dir.iterdir():
        if not p.is_file():
            continue
        if p.name.startswith("edgar_") and p.suffix in (".md", ".yaml"):
            p.unlink()
            n += 1
    return n


def row_to_dict(row: Any) -> dict[str, Any]:
    """Normalize a HF dataset row to a string-keyed dict."""
    if isinstance(row, dict):
        return dict(row)
    if hasattr(row, "keys") and callable(row.keys):
        return {str(k): row[k] for k in row.keys()}  # type: ignore[operator, index]
    raise TypeError(f"Unexpected row type: {type(row)}")


__all__ = [
    "SECTION_HEADERS",
    "clean_edgar_exports",
    "row_to_dict",
    "row_to_markdown",
    "row_to_sidecar_metadata",
    "row_to_stem",
    "sidecar_yaml_dict",
    "write_export_pair",
]
