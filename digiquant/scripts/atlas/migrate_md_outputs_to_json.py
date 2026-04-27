#!/usr/bin/env python3
"""
One-time / occasional helper: migrate markdown weekly + deep-dive files next to
`data/agent-cache/weekly` and `data/agent-cache/deep-dives` into JSON artifacts.
Moves *.md into `data/agent-cache/_migrated_md/{weekly,deep-dives}/`.
"""
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
AGENT_CACHE = ROOT / "data" / "agent-cache"


def _weekly_from_md(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    m = re.search(r"Generated:\s*(\d{4}-\d{2}-\d{2})", text)
    date = m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    m2 = re.search(r"(\d{4}-W\d{2})", md_path.stem)
    week_label = m2.group(1) if m2 else md_path.stem
    ex_lines = []
    in_ex = False
    for line in text.splitlines():
        if line.strip().startswith("## Week in Review"):
            in_ex = True
            continue
        if in_ex:
            if line.startswith("## ") and "Executive" not in line:
                break
            if line.startswith("## ") and "Executive" in line:
                continue
            ex_lines.append(line)
    executive = "\n".join(ex_lines).strip() or text[:2000]
    kt = ""
    if "## Week's Key Takeaway" in text:
        kt = text.split("## Week's Key Takeaway")[-1].split("---")[0].strip()
    elif "## Key Takeaway" in text:
        kt = text.split("## Key Takeaway")[-1].split("---")[0].strip()

    def rf(b, f, s):
        return {"baseline": b, "friday": f, "weekly_shift": s}

    body = {
        "executive_summary": executive[:8000],
        "daily_bias_shifts": [
            {
                "label": "Sun",
                "date": date,
                "macro": "See full_document_markdown",
                "equities": "—",
                "crypto": "—",
                "bonds": "—",
                "key_catalyst": "Baseline week",
            }
        ],
        "regime_summary": {
            "growth": rf("See markdown", "—", "TBD"),
            "inflation": rf("See markdown", "—", "TBD"),
            "policy": rf("See markdown", "—", "TBD"),
            "risk_appetite": rf("See markdown", "—", "TBD"),
            "net_change": "See full_document_markdown for detail.",
        },
        "asset_class_summary": {
            "equities": {"weekly_bias": "See markdown", "highlights": "—"},
            "crypto": {"weekly_bias": "See markdown", "highlights": "—"},
            "bonds": {"weekly_bias": "See markdown", "highlights": "—"},
            "commodities": {"weekly_bias": "See markdown", "highlights": "—"},
            "forex": {"weekly_bias": "See markdown", "highlights": "—"},
        },
        "thesis_review": [
            {
                "thesis_id": "migrated",
                "thesis": "Migrated from markdown; see full_document_markdown",
                "weekly_evidence": "—",
                "status_change": "unchanged",
            }
        ],
        "next_week_setup": {
            "key_events": [
                {
                    "day": "—",
                    "date": date,
                    "event": "See full_document_markdown",
                    "why_it_matters": "Legacy migration",
                }
            ],
            "heading_in_bias": "See full_document_markdown",
            "primary_watch": "See full_document_markdown",
            "positions_to_review": [],
        },
        "key_takeaway": kt[:1200] if kt else executive[:1200],
        "full_document_markdown": text,
    }
    return {
        "schema_version": "1.1",
        "doc_type": "weekly_digest",
        "date": date,
        "week_label": week_label,
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": {"start": date, "end": date},
            "sources": {"baseline_date": date, "delta_dates": []},
            "tags": ["migrated_from_md"],
        },
        "body": body,
    }


def _deep_dive_from_md(md_path: Path) -> dict:
    text = md_path.read_text(encoding="utf-8")
    m = re.match(r"(\d{4}-\d{2}-\d{2})", md_path.stem)
    date = m.group(1) if m else datetime.now(timezone.utc).strftime("%Y-%m-%d")
    title = md_path.stem
    if m:
        title = md_path.stem[len(m.group(1)) + 1 :].replace("-", " ").strip() or md_path.stem
    headings = []
    for line in text.splitlines():
        hm = re.match(r"^(#{1,6})\s+(.+)$", line.strip())
        if hm:
            headings.append({"heading": hm.group(2).strip(), "level": len(hm.group(1))})
    return {
        "schema_version": "1.0",
        "doc_type": "deep_dive",
        "date": date,
        "title": title,
        "meta": {"generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "tags": ["migrated_from_md"]},
        "body": {"markdown": text, "sections": headings},
    }


def main() -> int:
    weekly_dir = AGENT_CACHE / "weekly"
    arch_weekly = AGENT_CACHE / "_migrated_md" / "weekly"
    arch_weekly.mkdir(parents=True, exist_ok=True)
    for md in sorted(weekly_dir.glob("*.md")):
        data = _weekly_from_md(md)
        out = weekly_dir / (md.stem + ".json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.move(str(md), arch_weekly / md.name)
        print("weekly:", md.name, "->", out.name)

    deep_dir = AGENT_CACHE / "deep-dives"
    arch_deep = AGENT_CACHE / "_migrated_md" / "deep-dives"
    arch_deep.mkdir(parents=True, exist_ok=True)
    for md in sorted(deep_dir.glob("*.md")):
        data = _deep_dive_from_md(md)
        out = deep_dir / (md.stem + ".json")
        out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        shutil.move(str(md), arch_deep / md.name)
        print("deep-dive:", md.name, "->", out.name)

    return 0


if __name__ == "__main__":
    sys.exit(main())
