"""Atlas dashboard digest parsing — shared by update_tearsheet and backfill scripts (SIMP-011)."""

from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from pathlib import Path

logger = logging.getLogger(__name__)

FILE_IO_ERRORS = (OSError, UnicodeDecodeError)
JSON_IO_ERRORS = (*FILE_IO_ERRORS, json.JSONDecodeError)
YFINANCE_FETCH_ERRORS = (OSError, ValueError, KeyError, TypeError)
REMOTE_UPSERT_ERRORS = (OSError, ValueError, TypeError, KeyError, RuntimeError)

FILE_CLASSIFICATION = {
    "DIGEST.md": {"phase": 7, "category": "synthesis", "segment": "digest"},
    "DIGEST-DELTA.md": {"phase": 7, "category": "synthesis", "segment": "digest-delta"},
    "alt-data.md": {"phase": 1, "category": "alt-data", "segment": "alt-data"},
    "institutional.md": {"phase": 2, "category": "institutional", "segment": "institutional"},
    "macro.md": {"phase": 3, "category": "macro", "segment": "macro"},
    "bonds.md": {"phase": 4, "category": "asset-class", "segment": "bonds"},
    "commodities.md": {"phase": 4, "category": "asset-class", "segment": "commodities"},
    "forex.md": {"phase": 4, "category": "asset-class", "segment": "forex"},
    "crypto.md": {"phase": 4, "category": "asset-class", "segment": "crypto"},
    "international.md": {"phase": 4, "category": "asset-class", "segment": "international"},
    "equities.md": {"phase": 5, "category": "equity", "segment": "us-equities"},
    "us-equities.md": {"phase": 5, "category": "equity", "segment": "us-equities"},
    "rebalance-decision.md": {"phase": 7, "category": "portfolio", "segment": "rebalance"},
}

SECTOR_NAMES = {
    "technology": "Technology",
    "healthcare": "Healthcare",
    "energy": "Energy",
    "financials": "Financials",
    "consumer-staples": "Consumer Staples",
    "consumer-disc": "Consumer Discretionary",
    "industrials": "Industrials",
    "utilities": "Utilities",
    "materials": "Materials",
    "real-estate": "Real Estate",
    "comms": "Communications",
}


def _extract_date(path: Path) -> str:
    match = re.search(r"(\d{4}-\d{2}-\d{2})", str(path))
    return match.group(1) if match else "1970-01-01"


def load_portfolio_json(portfolio_path: Path) -> tuple[list, list, dict, str]:
    """Load portfolio.json → (positions, proposed_positions, constraints, investor_currency)."""
    if not portfolio_path.exists():
        return [], [], {}, "USD"
    try:
        with portfolio_path.open(encoding="utf-8") as handle:
            data = json.load(handle)
        positions = data.get("positions", [])
        proposed = data.get("proposed_positions", [])
        constraints = data.get("constraints", {})
        investor_currency = data.get("investor_currency", "USD").upper()
        return positions, proposed, constraints, investor_currency
    except JSON_IO_ERRORS as exc:
        logger.warning("could not read portfolio.json: %s", exc)
        return [], [], {}, "USD"


def load_rebalance_decision(date_str: str, daily_dir: Path) -> list[dict] | None:
    """Extract proposed portfolio table from rebalance-decision.md."""
    rebal_path = daily_dir / date_str / "rebalance-decision.md"
    if not rebal_path.exists():
        return None
    try:
        content = rebal_path.read_text(encoding="utf-8")
    except FILE_IO_ERRORS as exc:
        logger.warning("rebalance-decision read failed for %s: %s", date_str, exc)
        return None
    rows = []
    for match in re.finditer(
        r"\|\s*([A-Z]{2,5})\s*\|\s*(\d+)%?\s*\|\s*(\d+)%?\s*\|\s*[^\|]+\|\s*(\w+)\s*\|",
        content,
    ):
        rows.append(
            {
                "ticker": match.group(1),
                "current_pct": int(match.group(2)),
                "recommended_pct": int(match.group(3)),
                "action": match.group(4),
            }
        )
    return rows if rows else None


def get_digest_files(daily_dir: Path) -> list[Path]:
    """Find daily digest markdown files (flat legacy or nested DIGEST.md folders)."""
    files: list[Path] = []
    if not daily_dir.exists():
        return files

    for item in daily_dir.iterdir():
        if item.is_file() and item.suffix == ".md" and re.match(r"\d{4}-\d{2}-\d{2}", item.stem):
            files.append(item)
        elif item.is_dir():
            digest = item / "DIGEST.md"
            if digest.exists() and digest.stat().st_size > 0:
                files.append(digest)

    files.sort(key=_extract_date)
    return files


def parse_digest(filepath: Path) -> dict:
    """Extract positioning, regime, bias, and lists from a digest markdown file."""
    content = filepath.read_text(encoding="utf-8")

    match_date = re.search(r"(\d{4}-\d{2}-\d{2})", str(filepath))
    date_str = match_date.group(1) if match_date else "Unknown"

    data: dict = {
        "date": date_str,
        "positions": [],
        "regime": "Unknown",
        "regime_label": "neutral",
        "bias": "Unknown",
        "regime_summary": "",
        "actionable": [],
        "risks": [],
        "theses": [],
    }

    alloc_pattern = r"-\s*\*\*([A-Z]+)\*\*(?:\s*\((.*?)\))?:\s*(\d+)%(?:\s*(?:—|-)\s*(.*))?"
    for match in re.finditer(alloc_pattern, content):
        ticker = match.group(1)
        name = (match.group(2) or ticker).strip()
        weight = float(match.group(3))
        rationale = (match.group(4) or "").strip()
        data["positions"].append(
            {
                "ticker": ticker,
                "name": name.title() if ticker == name else name,
                "weight": weight,
                "rationale": rationale,
            }
        )

    if not data["positions"]:
        portfolio_match = re.search(r"## Portfolio Positioning", content)
        if portfolio_match:
            section = content[portfolio_match.end() :]
            next_h2 = re.search(r"\n## ", section)
            if next_h2:
                section = section[: next_h2.start()]
            table_pat = r"^\|\s*([A-Z]{2,5})\s*\|\s*(\d+)%?\s*\|(.+)\|"
            for row_match in re.finditer(table_pat, section, re.MULTILINE):
                ticker = row_match.group(1)
                weight = float(row_match.group(2))
                cells = [cell.strip() for cell in row_match.group(3).split("|")]
                action = cells[-2] if len(cells) >= 2 else ""
                rationale = cells[-1] if cells else ""
                data["positions"].append(
                    {
                        "ticker": ticker,
                        "name": ticker,
                        "weight": weight,
                        "action": action,
                        "rationale": rationale,
                    }
                )

    regime_match = re.search(r"\*\*Overall Bias\*\*:\s*([^\n]+)", content)
    if regime_match:
        full_bias = regime_match.group(1).strip()
        data["bias"] = full_bias.split("—")[0].strip() if "—" in full_bias else full_bias
        data["regime"] = full_bias

        bias_lower = data["bias"].lower()
        if any(word in bias_lower for word in ["bullish", "risk-on"]):
            data["regime_label"] = "bullish"
        elif any(word in bias_lower for word in ["bearish", "risk-off"]):
            data["regime_label"] = "bearish"
        elif any(word in bias_lower for word in ["caution", "mixed", "conflicted", "transitional"]):
            data["regime_label"] = "caution"
        else:
            data["regime_label"] = "neutral"

        para = content[regime_match.end() :].lstrip().split("\n\n")[0]
        data["regime_summary"] = para.strip()

    def extract_list_under_heading(heading_re: str) -> list[str]:
        head_match = re.search(heading_re, content)
        if not head_match:
            return []
        sub_content = content[head_match.end() :].lstrip()
        lines: list[str] = []
        for line in sub_content.splitlines():
            if line.startswith("## "):
                break
            if line.strip().startswith("- ") or re.match(r"\d+\.\s+", line.strip()):
                lines.append(line.strip())
        return [re.sub(r"^(-\s*|\d+\.\s*)", "", line) for line in lines]

    data["actionable"] = extract_list_under_heading(r"## (?:⚡\s*)?Actionable Summary")
    data["risks"] = extract_list_under_heading(r"## (?:🚨\s*)?Risk Radar")

    thesis_match = re.search(r"## (?:📋\s*)?Thesis Tracker", content)
    if thesis_match:
        table_content = content[thesis_match.end() :]
        next_heading = re.search(r"\n## ", table_content)
        if next_heading:
            table_content = table_content[: next_heading.start()]
        rows = [
            line.strip()
            for line in table_content.splitlines()
            if line.strip().startswith("|") and not re.match(r"^\|[-\s|]+\|$", line.strip())
        ]
        if len(rows) >= 2:
            rows = rows[1:]
        for row in rows:
            cells = [cell.strip() for cell in row.split("|")[1:-1]]
            if len(cells) >= 5:
                data["theses"].append(
                    {
                        "id": cells[0],
                        "name": cells[1],
                        "vehicle": cells[2],
                        "invalidation": cells[3],
                        "status": cells[4],
                        "notes": cells[5] if len(cells) > 5 else "",
                    }
                )

    return data


def normalize_thesis_status(raw: str | None) -> str | None:
    """Normalize free-form thesis status (with emoji) to DB enum value."""
    if not raw:
        return None
    normalized = (
        raw.lower().replace("\u2705", "").replace("\u26a0\ufe0f", "").replace("\u274c", "").strip()
    )
    if "challenged" in normalized:
        return "CHALLENGED"
    if "confirmed" in normalized or "active" in normalized:
        return "ACTIVE"
    if "monitoring" in normalized:
        return "MONITORING"
    if "invalidated" in normalized:
        return "INVALIDATED"
    if "closed" in normalized:
        return "CLOSED"
    if "paused" in normalized or "hold" in normalized:
        return "PAUSED"
    if "new" in normalized:
        return "NEW"
    return "ACTIVE"


def read_md(filepath: Path) -> str:
    """Read a markdown file, returning content or an error placeholder."""
    try:
        return filepath.read_text(encoding="utf-8")
    except FILE_IO_ERRORS as exc:
        logger.warning("markdown read failed for %s: %s", filepath, exc)
        return "_(Error reading file)_"


def detect_run_type(day_dir: Path) -> str:
    """Read _meta.json from a daily folder to determine baseline/delta."""
    meta = day_dir / "_meta.json"
    if meta.exists():
        try:
            with meta.open(encoding="utf-8") as handle:
                payload = json.load(handle)
            return payload.get("type", "baseline")
        except JSON_IO_ERRORS as exc:
            logger.warning("_meta.json read failed for %s: %s", day_dir.name, exc)
    return "baseline"


def load_snapshot_json(day_dir: Path) -> dict | None:
    """Load snapshot.json when present and populated (not scaffold placeholder)."""
    snap_path = day_dir / "snapshot.json"
    if not snap_path.exists():
        return None
    try:
        data = json.loads(snap_path.read_text(encoding="utf-8"))
    except JSON_IO_ERRORS as exc:
        logger.warning("snapshot.json read failed for %s: %s", day_dir.name, exc)
        return None
    if not data.get("regime") or data["regime"] == {}:
        return None
    return data


def load_all_markdowns(root: Path) -> list[dict]:
    """Scan agent-cache tree for timeline documents with phase/segment metadata."""
    docs: list[dict] = []

    daily_path = root / "data" / "agent-cache" / "daily"
    if daily_path.exists():
        for day_dir in sorted(daily_path.iterdir()):
            if not day_dir.is_dir():
                continue
            day_date = day_dir.name
            if not re.match(r"\d{4}-\d{2}-\d{2}", day_date):
                continue

            run_type = detect_run_type(day_dir)

            for md_file in sorted(day_dir.glob("*.md")):
                if md_file.name.startswith("."):
                    continue
                content = read_md(md_file)
                cls = FILE_CLASSIFICATION.get(md_file.name, {})
                segment_name = cls.get("segment", md_file.stem)
                is_delta_file = md_file.name == "DIGEST-DELTA.md"
                docs.append(
                    {
                        "title": segment_name.replace("-", " ").title(),
                        "type": "Daily Delta" if is_delta_file else "Daily Digest",
                        "date": day_date,
                        "path": str(md_file.relative_to(root)),
                        "content": content,
                        "phase": cls.get("phase"),
                        "category": cls.get("category", "output"),
                        "segment": segment_name,
                        "sector": None,
                        "runType": run_type,
                    }
                )

            sectors_dir = day_dir / "sectors"
            if sectors_dir.exists():
                for sector_file in sorted(sectors_dir.glob("*.md")):
                    if sector_file.name.startswith("."):
                        continue
                    content = read_md(sector_file)
                    stem = sector_file.stem.replace(".delta", "")
                    is_delta = sector_file.name.endswith(".delta.md")
                    sector_label = SECTOR_NAMES.get(stem, stem.replace("-", " ").title())
                    docs.append(
                        {
                            "title": f"{sector_label}{' Delta' if is_delta else ''}",
                            "type": "Daily Delta" if is_delta else "Daily Digest",
                            "date": day_date,
                            "path": str(sector_file.relative_to(root)),
                            "content": content,
                            "phase": 5,
                            "category": "sector",
                            "segment": stem,
                            "sector": sector_label,
                            "runType": run_type,
                        }
                    )

            deltas_dir = day_dir / "deltas"
            if deltas_dir.exists():
                for delta_file in sorted(deltas_dir.glob("*.delta.md")):
                    content = read_md(delta_file)
                    segment = delta_file.stem.replace(".delta", "")
                    cls = FILE_CLASSIFICATION.get(f"{segment}.md", {})
                    docs.append(
                        {
                            "title": f"{segment.replace('-', ' ').title()} Delta",
                            "type": "Daily Delta",
                            "date": day_date,
                            "path": str(delta_file.relative_to(root)),
                            "content": content,
                            "phase": cls.get("phase"),
                            "category": cls.get("category", "delta"),
                            "segment": segment,
                            "sector": None,
                            "runType": "delta",
                        }
                    )

            positions_dir = day_dir / "positions"
            if positions_dir.exists():
                for position_file in sorted(positions_dir.glob("*.md")):
                    content = read_md(position_file)
                    ticker = position_file.stem.upper()
                    docs.append(
                        {
                            "title": f"{ticker} Position Analysis",
                            "type": "Daily Digest",
                            "date": day_date,
                            "path": str(position_file.relative_to(root)),
                            "content": content,
                            "phase": 7,
                            "category": "portfolio",
                            "segment": ticker.lower(),
                            "sector": None,
                            "runType": run_type,
                        }
                    )

    for sub, label, category in [
        ("weekly", "Weekly Rollup", "rollup"),
        ("monthly", "Monthly Summary", "rollup"),
        ("deep-dives", "Deep Dive", "deep-dive"),
    ]:
        rollup_path = root / "data" / "agent-cache" / sub
        if not rollup_path.exists():
            continue
        for md_file in sorted(rollup_path.glob("*.md")):
            if md_file.name.startswith("."):
                continue
            content = read_md(md_file)
            date_match = re.match(r"(\d{4}-\d{2}-\d{2})", md_file.stem)
            file_date = (
                date_match.group(1)
                if date_match
                else datetime.fromtimestamp(os.path.getmtime(md_file)).strftime("%Y-%m-%d")
            )
            docs.append(
                {
                    "title": md_file.stem.replace("-", " ").title(),
                    "type": label,
                    "date": file_date,
                    "path": str(md_file.relative_to(root)),
                    "content": content,
                    "phase": None,
                    "category": category,
                    "segment": md_file.stem,
                    "sector": None,
                    "runType": None,
                }
            )

    return docs


def load_prefetched_prices(root: Path) -> dict[str, dict]:
    """Load latest ``data/quotes.json`` as ``{ticker: snapshot}`` (SIMP-011 shared helper).

    Used when yfinance is unavailable (CI/sandbox). ``root`` is the digiquant repo root.
    """
    daily_dir = root / "data" / "agent-cache" / "daily"
    if not daily_dir.exists():
        return {}
    for day_dir in sorted(daily_dir.iterdir(), reverse=True):
        quotes_file = day_dir / "data" / "quotes.json"
        if not quotes_file.exists():
            continue
        try:
            raw = json.loads(quotes_file.read_text(encoding="utf-8"))
            snapshots = raw.get("snapshots", [])
            return {s["ticker"]: s for s in snapshots if "error" not in s}
        except (*JSON_IO_ERRORS, KeyError, TypeError) as exc:
            logger.warning("prefetched quotes skipped for %s: %s", quotes_file, exc)
            continue
    return {}
