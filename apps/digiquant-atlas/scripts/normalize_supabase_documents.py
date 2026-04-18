#!/usr/bin/env python3
"""
Audit and migrate Supabase `documents` rows toward canonical JSON schemas in
`templates/schemas/` and `templates/digest-snapshot-schema.json`.

Usage:
  python3 scripts/normalize_supabase_documents.py audit [--json]
  python3 scripts/normalize_supabase_documents.py migrate [--dry-run|--apply] [--only-key SUBSTR]

Legacy markdown-first rows (e.g. deliberation.md) are wrapped into valid JSON with
provenance in meta/footer_notes; structured semantics may still need human review.

Requires: pip install jsonschema supabase python-dotenv
Env: SUPABASE_URL, SUPABASE_SERVICE_KEY (e.g. config/supabase.env)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

try:
    import jsonschema
except ImportError:
    print("Install jsonschema: pip install jsonschema", file=sys.stderr)
    raise SystemExit(2)

try:
    from supabase import create_client
except ImportError:
    print("Install supabase: pip install supabase", file=sys.stderr)
    raise SystemExit(2)

try:
    from dotenv import load_dotenv
except ImportError:
    load_dotenv = None  # type: ignore

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "templates" / "schemas"
DIGEST_SCHEMA = ROOT / "templates" / "digest-snapshot-schema.json"
DELTA_REQ_SCHEMA = ROOT / "templates" / "delta-request-schema.json"

DOC_TYPE_TO_SCHEMA = {
    "weekly_digest": "weekly-digest.schema.json",
    "monthly_digest": "monthly-digest.schema.json",
    "master_digest": "master-digest.schema.json",
    "delta_segment": "delta-segment.schema.json",
    "rebalance_decision": "rebalance-decision.schema.json",
    "deep_dive": "deep-dive.schema.json",
    "sector_report": "sector-report.schema.json",
    "asset_recommendation": "asset-recommendation.schema.json",
    "deliberation_transcript": "deliberation-transcript.schema.json",
    "delta_digest": "delta-digest.schema.json",
    "evolution_quality_log": "evolution-quality-log.schema.json",
    "evolution_sources": "evolution-sources.schema.json",
    "evolution_proposals": "evolution-proposals.schema.json",
    "research_delta": "research-delta.schema.json",
    "research_baseline_manifest": "research-baseline-manifest.schema.json",
    "document_delta": "document-delta.schema.json",
    "research_changelog": "research-changelog.schema.json",
    "market_thesis_exploration": "market-thesis-exploration.schema.json",
    "thesis_vehicle_map": "thesis-vehicle-map.schema.json",
    "pm_allocation_memo": "pm-allocation-memo.schema.json",
    "deliberation_session_index": "deliberation-session-index.schema.json",
}

WEEKLY_BODY_KEYS = frozenset(
    {
        "executive_summary",
        "daily_bias_shifts",
        "regime_summary",
        "asset_class_summary",
        "thesis_review",
        "next_week_setup",
        "key_takeaway",
        "full_document_markdown",
    }
)


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _sb():
    import os

    if load_dotenv:
        load_dotenv(ROOT / "config" / "supabase.env")
        load_dotenv()
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


def fetch_all_documents(sb, only_key_substr: Optional[str]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    start = 0
    page = 500
    while True:
        q = sb.table("documents").select("*").order("date", desc=False)
        if only_key_substr:
            q = q.ilike("document_key", f"%{only_key_substr}%")
        res = q.range(start, start + page - 1).execute()
        batch = getattr(res, "data", None) or []
        rows.extend(batch)
        if len(batch) < page:
            break
        start += page
    return rows


def _is_digest_snapshot(p: Dict[str, Any]) -> bool:
    return (
        p.get("run_type") in ("baseline", "delta")
        and "segment_biases" in p
        and "sector_scorecard" in p
        and "narrative" in p
    )


def _is_delta_request(p: Dict[str, Any]) -> bool:
    return isinstance(p.get("ops"), list) and isinstance(p.get("changed_paths"), list) and "baseline_date" in p


def classify_payload(document_key: str, payload: Any) -> str:
    """Return validator kind: digest_snapshot, delta_request, or doc_type string, or unknown."""
    if not isinstance(payload, dict):
        return "non_object"
    key = (document_key or "").lower()
    dt = str(payload.get("doc_type") or "")
    if dt in DOC_TYPE_TO_SCHEMA:
        return dt
    if dt == "markdown_legacy":
        if key == "digest" or key.endswith("/digest"):
            b = payload.get("body")
            if isinstance(b, dict) and isinstance(b.get("markdown"), str) and b["markdown"].strip():
                return "legacy_digest_markdown_only"
        if key.endswith("deliberation.md"):
            return "legacy_deliberation_md"
        if key.endswith("rebalance-decision.md"):
            return "legacy_rebalance_md"
        if key.startswith("deep-dives/") and key.endswith(".md"):
            return "legacy_deep_dive_md"
        if key.startswith("weekly/") and key.endswith(".md"):
            return "legacy_weekly_md"
        return "legacy_markdown_segment"
    if _is_digest_snapshot(payload):
        return "digest_snapshot"
    # Markdown-only digest without markdown_legacy doc_type
    if key == "digest" or key.endswith("/digest"):
        b = payload.get("body")
        if isinstance(b, dict) and isinstance(b.get("markdown"), str) and b["markdown"].strip():
            return "legacy_digest_markdown_only"
    if key.endswith("delta-request.json") or _is_delta_request(payload):
        return "delta_request"
    if key.endswith("rebalance-decision.json"):
        b = payload.get("body")
        if str(payload.get("doc_type") or "") == "rebalance_decision" or (
            isinstance(b, dict) and ("rebalance_table" in b or "proposed_portfolio" in b)
        ):
            return "rebalance_decision"
        if isinstance(payload.get("trades"), list) or isinstance(payload.get("post_trade_portfolio"), dict):
            return "legacy_rebalance_trades_json"
    if key.endswith("deliberation.md") or (key.endswith("deliberation-transcript.json") and not payload.get("doc_type")):
        return "legacy_deliberation_md"
    if key.endswith("rebalance-decision.md") or ("rebalance" in key and key.endswith(".md") and not dt):
        return "legacy_rebalance_md"
    if key == "digest-delta":
        return "legacy_digest_delta"
    if key.startswith("deep-dives/") and key.endswith(".md"):
        return "legacy_deep_dive_md"
    if key.startswith("weekly/") and key.endswith(".json"):
        if payload.get("doc_type") == "weekly_digest":
            return "weekly_digest"
        return "legacy_weekly_partial"
    if document_key.endswith(".md") and payload.get("body") and isinstance(payload["body"], dict):
        if "markdown" in payload["body"] and not dt:
            return "legacy_markdown_segment"
    return "unknown"


def normalize_legacy_weekly_md(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    wl_match = re.search(r"(20\d{2}-W\d{2})", document_key, re.I)
    week_label = wl_match.group(1) if wl_match else f"{date_str[:4]}-W00"
    na = {"weekly_bias": "—", "highlights": "—"}
    return {
        "schema_version": "1.0",
        "doc_type": "weekly_digest",
        "date": date_str,
        "week_label": week_label,
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": {"start": date_str, "end": date_str},
            "sources": {"baseline_date": date_str, "delta_dates": []},
            "tags": ["migrated_from_weekly_md"],
        },
        "body": {
            "executive_summary": (md[:8000] if md else "See full_document_markdown.")[:8000],
            "daily_bias_shifts": [],
            "regime_summary": {
                "growth": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
                "inflation": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
                "policy": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
                "risk_appetite": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
                "net_change": "—",
            },
            "asset_class_summary": {
                "equities": na,
                "crypto": na,
                "bonds": na,
                "commodities": na,
                "forex": na,
            },
            "thesis_review": [],
            "next_week_setup": {
                "key_events": [],
                "heading_in_bias": "—",
                "primary_watch": "—",
                "positions_to_review": [],
            },
            "key_takeaway": (md[:1200] if md else "—")[:1200],
            "full_document_markdown": md[:500000] if md else None,
        },
    }


def schema_for_kind(kind: str) -> Optional[Dict[str, Any]]:
    if kind == "digest_snapshot":
        return _load_json(DIGEST_SCHEMA)
    if kind == "delta_request":
        return _load_json(DELTA_REQ_SCHEMA)
    fname = DOC_TYPE_TO_SCHEMA.get(kind)
    if not fname:
        return None
    return _load_json(SCHEMAS_DIR / fname)


def validate_payload(kind: str, payload: Dict[str, Any]) -> List[str]:
    schema = schema_for_kind(kind)
    if not schema:
        return [f"no schema for kind {kind!r}"]
    try:
        jsonschema.validate(instance=payload, schema=schema)
        return []
    except jsonschema.ValidationError as e:
        return [e.message]


def extract_markdown(payload: Dict[str, Any]) -> str:
    b = payload.get("body")
    if isinstance(b, dict):
        m = b.get("markdown")
        if isinstance(m, str):
            return m
    return ""


def normalize_legacy_deliberation(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    if len(md) > 39000:
        md = md[:39000] + "\n\n…(truncated for schema maxLength)…"
    kind = "baseline_full" if "weekly baseline" in md.lower()[:800] or "2026-w" in md.lower()[:800] else "delta_scoped"
    return {
        "schema_version": "1.0",
        "doc_type": "deliberation_transcript",
        "date": date_str,
        "meta": {
            "kind": kind,
            "delta_number": None,
            "triggers": ["migrated_from_legacy_payload"],
            "positions_reviewed": [],
        },
        "body": {
            "trigger_summary": [
                "Migrated from legacy deliberation storage; structured PM fields were not present. "
                "Canonical prose is under 'Archived markdown'."
            ],
            "rounds": [
                {
                    "label": "Archived markdown",
                    "sections": [{"heading": "Original transcript", "markdown": md or "_empty_"}],
                }
            ],
            "final_decisions": [
                {
                    "ticker": "LEGACY",
                    "analyst_recommendation": "See archived markdown",
                    "pm_decision": "See archived markdown",
                    "invalidation_condition": None,
                }
            ],
            "thesis_updates": [
                {
                    "thesis_id": "N/A",
                    "status": "UNKNOWN",
                    "note": "Unstructured legacy transcript; verify manually if needed.",
                }
            ],
            "footer_notes": f"migrated_from={document_key}",
        },
    }


def _bias_to_schema_ow_uw_n(raw: Any) -> str:
    b = str(raw or "N").strip().upper()
    if b in ("N", "NEUTRAL", ""):
        return "N"
    if "UNDER" in b or b == "UW":
        return "UW"
    if "OVER" in b or b == "OW" or "DEFENSIVE" in b:
        return "OW"
    if b in ("OW", "UW", "N"):
        return b
    return "N"


def _confidence_schema(raw: Any) -> str:
    c = str(raw or "Medium").strip()
    return c if c in ("High", "Medium", "Low") else "Medium"


def coerce_sector_scorecard(payload: Dict[str, Any]) -> None:
    """Mutate digest: sector_scorecard may be a dict keyed by sector slug; schema expects an array."""
    ss = payload.get("sector_scorecard")
    rows: List[Dict[str, Any]] = []
    if isinstance(ss, dict):
        for sector_key, row in ss.items():
            if not isinstance(row, dict):
                continue
            rows.append(
                {
                    "sector": str(row.get("sector") or sector_key)[:120],
                    "etf": str(row.get("etf") or "")[:12],
                    "bias": _bias_to_schema_ow_uw_n(row.get("bias")),
                    "confidence": _confidence_schema(row.get("confidence")),
                    "key_driver": str(row.get("key_driver") or "")[:200],
                }
            )
        payload["sector_scorecard"] = rows
    elif isinstance(ss, list):
        fixed: List[Dict[str, Any]] = []
        for row in ss:
            if not isinstance(row, dict):
                continue
            fixed.append(
                {
                    "sector": str(row.get("sector") or "")[:120],
                    "etf": str(row.get("etf") or "")[:12],
                    "bias": _bias_to_schema_ow_uw_n(row.get("bias")),
                    "confidence": _confidence_schema(row.get("confidence")),
                    "key_driver": str(row.get("key_driver") or "")[:200],
                }
            )
        payload["sector_scorecard"] = fixed


def normalize_legacy_rebalance_trades_json(
    document_key: str, date_str: str, payload: Dict[str, Any]
) -> Dict[str, Any]:
    """Convert pre-schema rebalance JSON (trades + post_trade_portfolio) to rebalance_decision."""
    trades = payload.get("trades") if isinstance(payload.get("trades"), list) else []
    post = payload.get("post_trade_portfolio")
    if not isinstance(post, dict):
        post = {}

    action_map = {"SELL": "EXIT", "BUY": "ADD", "SELL_PARTIAL": "TRIM", "BUY_PARTIAL": "ADD"}

    def _urgency(u: Any) -> str:
        s = str(u or "").lower()
        return "HIGH" if "immediate" in s else "NORMAL"

    rebalance_table: List[Dict[str, Any]] = []
    exits: List[str] = []
    new_entries: List[str] = []
    largest_abs = 0.0
    largest_desc = "See trades"

    traded_ticks: set[str] = set()
    for t in trades:
        if not isinstance(t, dict):
            continue
        act = str(t.get("action") or "")
        tick = str(t.get("ticker") or "")[:12]
        if tick:
            traded_ticks.add(tick)
        from_w, to_w = t.get("from_weight_pct"), t.get("to_weight_pct")
        try:
            fw = float(from_w) if from_w is not None else 0.0
            tw = float(to_w) if to_w is not None else 0.0
        except (TypeError, ValueError):
            fw, tw = 0.0, 0.0
        ch = tw - fw
        if abs(ch) >= largest_abs:
            largest_abs = abs(ch)
            largest_desc = f"{tick} {fw:.0f}%→{tw:.0f}%"

        sch_action = action_map.get(act, "HOLD")
        if act.startswith("SELL") and tw == 0:
            sch_action = "EXIT"
            exits.append(tick)
        if act.startswith("BUY") and fw == 0 and tw > 0:
            new_entries.append(tick)

        rebalance_table.append(
            {
                "ticker": tick,
                "current_pct": fw,
                "recommended_pct": tw,
                "change_pct": round(ch, 4),
                "action": sch_action,
                "urgency": _urgency(t.get("urgency")),
                "rationale": str(t.get("reason") or "")[:2000],
            }
        )

    for tick, w in post.items():
        t = str(tick)[:12]
        if t in traded_ticks:
            continue
        try:
            wt = float(w)
        except (TypeError, ValueError):
            wt = 0.0
        rebalance_table.append(
            {
                "ticker": t,
                "current_pct": wt,
                "recommended_pct": wt,
                "change_pct": 0.0,
                "action": "HOLD",
                "urgency": "NORMAL",
                "rationale": "Unchanged (from legacy post_trade_portfolio).",
            }
        )

    rebalance_table.sort(key=lambda r: r["ticker"])

    positions: List[Dict[str, Any]] = []
    total = 0.0
    for tick, w in sorted(post.items(), key=lambda x: str(x[0])):
        t = str(tick)[:12]
        try:
            wt = float(w)
        except (TypeError, ValueError):
            wt = 0.0
        total += wt
        positions.append(
            {
                "ticker": t,
                "weight_pct": wt,
                "thesis_id": None,
                "status": str(payload.get("status") or "HOLD")[:64],
            }
        )

    delta_summary = {
        "changes_triggered": float(len(trades)),
        "held_count": float(sum(1 for r in rebalance_table if r["action"] == "HOLD")),
        "largest_move": largest_desc[:120],
        "new_entries": [x for x in new_entries if x][:32],
        "exits": [x for x in exits if x][:32],
    }

    trig = payload.get("triggers")
    trig_s = ""
    if isinstance(trig, list):
        trig_s = "; ".join(str(x) for x in trig[:24])

    pm_bits = [
        f"**Migrated** from legacy `trades` / `post_trade_portfolio` JSON (`{document_key}`).",
        f"**pm_decision:** {payload.get('pm_decision')}",
        f"**status:** {payload.get('status')}",
        f"**triggers:** {trig_s}" if trig_s else None,
        f"**notes:** {payload.get('notes')}",
        f"**next_review_trigger:** {payload.get('next_review_trigger')}",
        f"**cash_equivalent_pct:** {payload.get('cash_equivalent_pct')}",
        f"**regime_playbook:** target {payload.get('regime_playbook_target_pct')}% "
        f"(gap {payload.get('regime_playbook_gap')}%)",
        f"**deliberation_conducted:** {payload.get('deliberation_conducted')}",
    ]
    pm_notes = "\n\n".join(x for x in pm_bits if x)[:12000]

    thr = payload.get("regime_playbook_gap")
    try:
        threshold_pct = float(thr) if thr is not None else 5.0
    except (TypeError, ValueError):
        threshold_pct = 5.0

    return {
        "schema_version": "1.0",
        "doc_type": "rebalance_decision",
        "date": str(payload.get("date") or date_str)[:10],
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "threshold_pct": threshold_pct,
            "investor_currency": "USD",
            "tags": ["migrated_from_legacy_trades_json"],
        },
        "body": {
            "delta_summary": delta_summary,
            "rebalance_table": rebalance_table,
            "proposed_portfolio": {
                "positions": positions,
                "cash_residual_pct": max(0.0, round(100.0 - total, 4)) if total else None,
                "total_pct": round(total, 4) if total else None,
            },
            "pm_notes": pm_notes,
            "invalidation_watch": [],
        },
    }


def normalize_legacy_rebalance(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    return {
        "schema_version": "1.0",
        "doc_type": "rebalance_decision",
        "date": date_str,
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "threshold_pct": 5,
            "investor_currency": "USD",
            "tags": ["migrated_from_legacy_md"],
        },
        "body": {
            "delta_summary": {
                "changes_triggered": 0,
                "held_count": 0,
                "largest_move": "See PM notes (legacy markdown)",
                "new_entries": [],
                "exits": [],
            },
            "rebalance_table": [],
            "proposed_portfolio": {"positions": [], "cash_residual_pct": None, "total_pct": None},
            "pm_notes": (md or "_empty_")[:12000],
            "invalidation_watch": [
                {
                    "ticker": "N/A",
                    "current_level": None,
                    "exit_trigger": None,
                    "distance": None,
                    "action_if_triggered": "See archived markdown in pm_notes",
                }
            ],
        },
    }


def normalize_legacy_digest_delta(date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    return {
        "schema_version": "1.0",
        "doc_type": "delta_digest",
        "date": date_str,
        "meta": {
            "baseline_date": date_str,
            "week_label": None,
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "delta_number": 1,
            "segments_changed": None,
        },
        "body": {
            "delta_summary": md[:8000] if md else "Legacy digest-delta; see sections_markdown.",
            "changed_segments": [],
            "carried_forward_segments": [],
            "sections_markdown": md[:200000] if md else None,
        },
    }


def _truncate_thesis_review(items: Any) -> Any:
    if not isinstance(items, list):
        return []
    out = []
    for it in items:
        if not isinstance(it, dict):
            continue
        row = deepcopy(it)
        th = str(row.get("thesis") or "")
        if len(th) > 200:
            row["thesis"] = th[:197] + "…"
        out.append(row)
    return out


def normalize_legacy_weekly(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    if isinstance(payload.get("body"), dict):
        body = payload["body"]
    else:
        body = {k: payload[k] for k in WEEKLY_BODY_KEYS if k in payload}
    if not body:
        body = {}
    filtered = {k: body[k] for k in WEEKLY_BODY_KEYS if k in body}
    # Ensure required keys exist minimally
    if "executive_summary" not in filtered:
        filtered["executive_summary"] = str(body.get("executive_summary") or "See full_document_markdown.")[:8000]
    if "key_takeaway" not in filtered:
        filtered["key_takeaway"] = str(body.get("key_takeaway") or filtered.get("executive_summary", ""))[:1200]
    if "daily_bias_shifts" not in filtered:
        filtered["daily_bias_shifts"] = []
    if "regime_summary" not in filtered:
        filtered["regime_summary"] = {
            "growth": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
            "inflation": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
            "policy": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
            "risk_appetite": {"baseline": "—", "friday": "—", "weekly_shift": "—"},
            "net_change": "—",
        }
    if "asset_class_summary" not in filtered:
        na = {"weekly_bias": "—", "highlights": "—"}
        filtered["asset_class_summary"] = {
            "equities": na,
            "crypto": na,
            "bonds": na,
            "commodities": na,
            "forex": na,
        }
    if "thesis_review" not in filtered:
        filtered["thesis_review"] = []
    filtered["thesis_review"] = _truncate_thesis_review(filtered.get("thesis_review"))
    if "next_week_setup" not in filtered:
        filtered["next_week_setup"] = {
            "key_events": [],
            "heading_in_bias": "—",
            "primary_watch": "—",
            "positions_to_review": [],
        }
    wl_match = re.search(r"(20\d{2}-W\d{2})", document_key, re.I)
    week_label = wl_match.group(1) if wl_match else f"{date_str[:4]}-W00"
    return {
        "schema_version": "1.0",
        "doc_type": "weekly_digest",
        "date": date_str,
        "week_label": week_label,
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "date_range": {"start": date_str, "end": date_str},
            "sources": {"baseline_date": date_str, "delta_dates": []},
            "tags": ["migrated_from_partial_weekly_json"],
        },
        "body": filtered,
    }


def normalize_legacy_deep_dive(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    raw_title = document_key.split("/")[-1].replace(".md", "").replace("-", " ")
    title = (raw_title[:200] if raw_title else "Deep dive")[:200]
    return {
        "schema_version": "1.0",
        "doc_type": "deep_dive",
        "date": date_str,
        "title": title or "Deep dive",
        "meta": {
            "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            "tags": ["migrated_from_md"],
        },
        "body": {"markdown": md or "_empty_", "summary": None},
    }


def normalize_markdown_segment(document_key: str, date_str: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    md = extract_markdown(payload)
    seg_hint = document_key.split("/")[-1].replace(".md", "")
    base_summary = (md[:3950] if md else f"Legacy segment {document_key}")[:3950]
    summary = f"[migrated_from={document_key}]\n{base_summary}"[:4000]
    return {
        "schema_version": "1.0",
        "doc_type": "research_delta",
        "date": date_str,
        "baseline_date": date_str,
        "run_type": "delta",
        "published_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "no_change": False,
        "segments": {
            "macro": md if "macro" in document_key.lower() else f"(Segment {seg_hint})\n\n{md}"[:12000],
            "crypto": md if "crypto" in document_key.lower() else "—",
            "sentiment": md if "sentiment" in document_key.lower() else "—",
            "sectors": md if "sector" in document_key.lower() else "—",
            "international": md if "international" in document_key.lower() else "—",
        },
        "summary": summary,
    }


REGIME_ALLOWED = frozenset({"bias", "label", "conviction", "summary", "dominant_force", "factors"})

SEGMENT_BIAS_KEYS = (
    "macro",
    "bonds",
    "commodities",
    "forex",
    "crypto",
    "international",
    "us_equities",
    "alt_data",
    "institutional",
)


def coerce_segment_biases(p: Dict[str, Any]) -> None:
    sb = p.get("segment_biases")
    if not isinstance(sb, dict):
        return
    out: Dict[str, Any] = {}
    for k in SEGMENT_BIAS_KEYS:
        v = sb.get(k)
        if isinstance(v, str):
            out[k] = {
                "bias": v[:200],
                "confidence": "Medium",
                "key_driver": "Legacy segment bias string coerced to object.",
            }
        elif isinstance(v, dict):
            conf = v.get("confidence")
            if conf not in ("High", "Medium", "Low"):
                conf = "Medium"
            out[k] = {
                "bias": str(v.get("bias") or "Neutral")[:200],
                "confidence": conf,
                "key_driver": str(v.get("key_driver") or "")[:200],
            }
        else:
            out[k] = {"bias": "Neutral", "confidence": "Medium", "key_driver": "—"}
    p["segment_biases"] = out


def coerce_regime_factors_strings(p: Dict[str, Any]) -> None:
    r = p.get("regime")
    if not isinstance(r, dict):
        return
    fac = r.get("factors")
    if not isinstance(fac, dict):
        return
    for k in ("growth", "inflation", "policy", "risk_appetite"):
        v = fac.get(k)
        if isinstance(v, dict):
            try:
                fac[k] = json.dumps(v, ensure_ascii=False)[:2000]
            except TypeError:
                fac[k] = str(v)[:2000]
        elif v is not None and not isinstance(v, str):
            fac[k] = str(v)[:2000]


def prune_digest_regime(p: Dict[str, Any]) -> None:
    r = p.get("regime")
    if not isinstance(r, dict):
        return
    for k in list(r.keys()):
        if k not in REGIME_ALLOWED:
            r.pop(k, None)
    c = r.get("conviction")
    if c not in ("High", "Medium", "Low"):
        s = str(c or "").lower()
        if "high" in s:
            r["conviction"] = "High"
        elif "low" in s:
            r["conviction"] = "Low"
        else:
            r["conviction"] = "Medium"
    coerce_regime_factors_strings(p)


def coerce_market_data_values(p: Dict[str, Any]) -> None:
    md = p.get("market_data")
    if not isinstance(md, dict):
        return
    for k, v in list(md.items()):
        if isinstance(v, (dict, list)):
            try:
                md[k] = json.dumps(v, ensure_ascii=False)[:8000]
            except TypeError:
                md[k] = str(v)[:8000]


def coerce_portfolio_posture(p: Dict[str, Any]) -> None:
    port = p.get("portfolio")
    if not isinstance(port, dict):
        return
    po = port.get("posture")
    if po in ("Defensive", "Neutral", "Offensive"):
        return
    s = str(po or "").lower()
    if "defensive" in s:
        port["posture"] = "Defensive"
    elif "offensive" in s or "risk-on" in s:
        port["posture"] = "Offensive"
    else:
        port["posture"] = "Neutral"


def _merge_top_level_thesis_tracker_into_narrative(p: Dict[str, Any]) -> None:
    """Move legacy top-level thesis_tracker into narrative.thesis_tracker (string)."""
    if "thesis_tracker" not in p:
        return
    tt = p.pop("thesis_tracker")
    nar = p.get("narrative")
    if not isinstance(nar, dict):
        return
    if isinstance(tt, str):
        block = tt
    else:
        try:
            block = json.dumps(tt, ensure_ascii=False, indent=2)
        except TypeError:
            block = str(tt)
    block = block[:12000]
    prev = nar.get("thesis_tracker")
    if isinstance(prev, str) and prev.strip():
        nar["thesis_tracker"] = (prev.strip() + "\n\n" + block)[:12000]
    else:
        nar["thesis_tracker"] = block


def ensure_digest_schema_version(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = deepcopy(payload)
    if "schema_version" not in p:
        p["schema_version"] = "1.0"
    # digest-snapshot-schema.json has additionalProperties: false
    p.pop("generated_at", None)
    _merge_top_level_thesis_tracker_into_narrative(p)
    prune_digest_regime(p)
    coerce_portfolio_posture(p)
    coerce_market_data_values(p)
    coerce_sector_scorecard(p)
    coerce_segment_biases(p)
    return p


def sanitize_delta_request(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = deepcopy(payload)
    ops = p.get("ops")
    if isinstance(ops, list):
        for op in ops:
            if not isinstance(op, dict):
                continue
            r = op.get("reason")
            if isinstance(r, str) and len(r) > 240:
                op["reason"] = r[:237] + "…"
    return p


EVOLUTION_SOURCES_TOP = frozenset({"schema_version", "doc_type", "date", "title", "meta", "body"})


def _coerce_source_ratings(raw: Any) -> List[Dict[str, Any]]:
    out: List[Dict[str, Any]] = []
    if not isinstance(raw, list):
        return out
    for x in raw:
        if not isinstance(x, dict):
            continue
        out.append(
            {
                "name": str(x.get("name") or x.get("source") or "unnamed")[:120],
                "reliability": str(x.get("reliability") or x.get("tier") or "—")[:32],
                "notes": str(x.get("notes") or x.get("comment") or "")[:2000],
            }
        )
    return out


def normalize_evolution_sources_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = deepcopy(payload)
    p["doc_type"] = "evolution_sources"
    if not p.get("title"):
        p["title"] = "Evolution sources"
    notes = ""
    ratings: List[Dict[str, Any]] = []
    b0 = p.get("body")
    if isinstance(b0, dict):
        notes = str(b0.get("notes") or "")
        if isinstance(b0.get("source_ratings"), list):
            ratings = _coerce_source_ratings(b0["source_ratings"])
    raw_sources = p.pop("sources", None)
    if raw_sources is not None:
        ratings = ratings + _coerce_source_ratings(raw_sources)
    p["body"] = {"source_ratings": ratings, "notes": notes[:8000]}
    for k in list(p.keys()):
        if k not in EVOLUTION_SOURCES_TOP:
            p.pop(k, None)
    return p


def sanitize_evolution_proposals_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = deepcopy(payload)
    b = p.get("body")
    if not isinstance(b, dict) or not isinstance(b.get("proposals"), list):
        return p
    fixed: List[Dict[str, Any]] = []
    for pr in b["proposals"]:
        if not isinstance(pr, dict):
            continue
        item: Dict[str, Any] = {
            "id": str(pr.get("id") or "proposal-unknown")[:32],
            "title": str(pr.get("title") or "")[:200],
            "problem": str(pr.get("problem") or "")[:4000],
            "proposal": str(pr.get("proposal") or "")[:4000],
            "priority": str(pr.get("priority") or "P3")[:16],
        }
        if pr.get("status") is not None:
            item["status"] = str(pr["status"])[:32]
        fixed.append(item)
    b["proposals"] = fixed
    return p


def sanitize_rebalance_decision_payload(payload: Dict[str, Any]) -> Dict[str, Any]:
    p = deepcopy(payload)
    if str(p.get("doc_type") or "") != "rebalance_decision":
        p["doc_type"] = "rebalance_decision"
    m = p.get("meta")
    if isinstance(m, dict):
        p["meta"] = {k: v for k, v in m.items() if k in ("generated_at", "threshold_pct", "investor_currency", "tags")}
    b = p.get("body")
    if isinstance(b, dict):
        ds = b.get("delta_summary")
        if isinstance(ds, dict):
            lm = ds.get("largest_move")
            if isinstance(lm, str) and len(lm) > 120:
                ds["largest_move"] = lm[:117] + "…"
            for arr_key in ("new_entries", "exits"):
                arr = ds.get(arr_key)
                if isinstance(arr, list):
                    ds[arr_key] = [(x[:12] if isinstance(x, str) else str(x)[:12]) for x in arr]
        rt = b.get("rebalance_table")
        if isinstance(rt, list):
            for row in rt:
                if isinstance(row, dict) and isinstance(row.get("rationale"), str) and len(row["rationale"]) > 2000:
                    row["rationale"] = row["rationale"][:1997] + "…"
        pm = b.get("pm_notes")
        if isinstance(pm, str) and len(pm) > 12000:
            b["pm_notes"] = pm[:11997] + "…"
    return p


def digest_payload_from_daily_snapshots(date_str: str) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Rebuild documents.digest payload from daily_snapshots.snapshot (canonical JSON)."""
    d = date_str[:10]
    sb = _sb()
    res = sb.table("daily_snapshots").select("snapshot").eq("date", d).limit(1).execute()
    rows = getattr(res, "data", None) or []
    if not rows:
        return None, [f"no daily_snapshots row for {d}"]
    snap = rows[0].get("snapshot")
    if not isinstance(snap, dict):
        return None, ["daily_snapshots.snapshot missing or not an object"]
    fixed = ensure_digest_schema_version(deepcopy(snap))
    err = validate_payload("digest_snapshot", fixed)
    return (fixed, []) if not err else (None, err)


def _render_digest_markdown_optional(snapshot: Dict[str, Any]) -> Optional[str]:
    try:
        import importlib.util

        path = ROOT / "scripts" / "materialize_snapshot.py"
        spec = importlib.util.spec_from_file_location("_mat_snap", path)
        mod = importlib.util.module_from_spec(spec)
        assert spec.loader is not None
        spec.loader.exec_module(mod)
        fn = getattr(mod, "render_digest_markdown", None)
        if callable(fn):
            return str(fn(snapshot))
    except Exception:
        pass
    return None


def row_display_doc_type(payload: Dict[str, Any], document_key: str) -> str:
    dt = str(payload.get("doc_type") or "")
    if dt:
        return dt
    if _is_digest_snapshot(payload):
        return "digest_snapshot"
    if document_key.endswith("delta-request.json") or document_key.lower().endswith("/delta-request.json"):
        return "delta_request"
    if document_key == "digest":
        return "digest_snapshot"
    return "unknown"


def migrate_row(row: Dict[str, Any]) -> Tuple[Optional[Dict[str, Any]], List[str]]:
    """Return (new_payload, []) to upsert, or (None, notes) if skip/fail."""
    document_key = str(row.get("document_key") or "")
    date_str = str(row.get("date") or "")[:10]
    payload = row.get("payload")
    if not isinstance(payload, dict):
        return None, ["skip: payload not object"]

    kind = classify_payload(document_key, payload)
    if kind == "unknown":
        if document_key.endswith(".md") and extract_markdown(payload) and not payload.get("doc_type"):
            kind = "legacy_markdown_segment"
        else:
            return None, ["skip: unknown shape"]

    if kind == "legacy_digest_markdown_only":
        fixed, err = digest_payload_from_daily_snapshots(date_str)
        if fixed is not None:
            return fixed, []
        return None, err

    # Already valid structured / digest / delta_request (metadata-only fixes below)
    if kind == "digest_snapshot":
        fixed = ensure_digest_schema_version(payload)
        err = validate_payload("digest_snapshot", fixed)
        if not err:
            return (fixed if fixed != payload else None), []
        return None, err

    if kind == "delta_request":
        fixed = sanitize_delta_request(payload)
        err = validate_payload("delta_request", fixed)
        if not err:
            return (fixed if fixed != payload else None), []
        return None, err

    if kind in DOC_TYPE_TO_SCHEMA:
        err = validate_payload(kind, payload)
        if not err:
            return None, []
        # weekly_digest: try stripping / wrapping from partial legacy shape inside
        if kind == "weekly_digest":
            wrapped = normalize_legacy_weekly(document_key, date_str, payload)
            err2 = validate_payload("weekly_digest", wrapped)
            return (wrapped, []) if not err2 else (None, err + err2)
        if kind == "rebalance_decision":
            fixed = sanitize_rebalance_decision_payload(payload)
            err2 = validate_payload(kind, fixed)
            return (fixed, []) if not err2 else (None, err + err2)
        if kind == "evolution_sources":
            fixed = normalize_evolution_sources_payload(payload)
            err2 = validate_payload(kind, fixed)
            return (fixed, []) if not err2 else (None, err + err2)
        if kind == "evolution_proposals":
            fixed = sanitize_evolution_proposals_payload(payload)
            err2 = validate_payload(kind, fixed)
            return (fixed, []) if not err2 else (None, err + err2)
        return None, err

    new_payload: Optional[Dict[str, Any]] = None
    if kind == "legacy_deliberation_md":
        new_payload = normalize_legacy_deliberation(document_key, date_str, payload)
    elif kind == "legacy_rebalance_trades_json":
        new_payload = normalize_legacy_rebalance_trades_json(document_key, date_str, payload)
    elif kind == "legacy_rebalance_md":
        new_payload = normalize_legacy_rebalance(document_key, date_str, payload)
    elif kind == "legacy_digest_delta":
        new_payload = normalize_legacy_digest_delta(date_str, payload)
    elif kind == "legacy_weekly_md":
        new_payload = normalize_legacy_weekly_md(document_key, date_str, payload)
    elif kind == "legacy_weekly_partial":
        new_payload = normalize_legacy_weekly(document_key, date_str, payload)
    elif kind == "legacy_deep_dive_md":
        new_payload = normalize_legacy_deep_dive(document_key, date_str, payload)
    elif kind == "legacy_markdown_segment":
        new_payload = normalize_markdown_segment(document_key, date_str, payload)
    else:
        return None, ["skip: no normalizer"]

    dt = str(new_payload.get("doc_type") or "")
    if dt == "delta_request":
        vkind = "delta_request"
    elif _is_digest_snapshot(new_payload) and "doc_type" not in new_payload:
        vkind = "digest_snapshot"
    else:
        vkind = dt
    if vkind == "delta_request":
        ve = validate_payload("delta_request", new_payload)
    elif vkind == "digest_snapshot":
        ve = validate_payload("digest_snapshot", new_payload)
    elif vkind in DOC_TYPE_TO_SCHEMA:
        ve = validate_payload(vkind, new_payload)
    else:
        ve = [f"cannot validate normalized kind {vkind!r}"]
    if ve:
        return None, ve
    return new_payload, []


# Must match chk_documents_doc_type (see supabase/migrations/014_documents_research_delta_doc_type.sql, 019).
DOC_TYPE_DB_COLUMN: Dict[str, str] = {
    "digest_snapshot": "Daily Digest",
    "delta_digest": "Daily Delta",
    "weekly_digest": "Weekly Rollup",
    "monthly_digest": "Monthly Summary",
    "deep_dive": "Deep Dive",
    "research_delta": "Research Delta",
    "research_baseline_manifest": "Research Baseline Manifest",
    "document_delta": "Document Delta",
    "research_changelog": "Research Changelog",
    "evolution_sources": "Evolution Sources",
    "evolution_quality_log": "Evolution Quality Log",
    "evolution_proposals": "Evolution Proposals",
}


def metadata_updates(document_key: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    dt = row_display_doc_type(payload, document_key)
    updates: Dict[str, Any] = {
        "segment": dt if dt != "unknown" else None,
    }
    col_dt = DOC_TYPE_DB_COLUMN.get(dt)
    if col_dt:
        updates["doc_type"] = col_dt
    return updates


def cmd_audit(args: argparse.Namespace) -> int:
    sb = _sb()
    rows = fetch_all_documents(sb, args.only_key)
    report: List[Dict[str, Any]] = []
    for row in rows:
        pk = row.get("id")
        dk = row.get("document_key")
        p = row.get("payload")
        kind = classify_payload(str(dk), p)
        errs: List[str] = []
        if isinstance(p, dict):
            if kind in DOC_TYPE_TO_SCHEMA or kind in ("digest_snapshot", "delta_request"):
                if kind == "digest_snapshot":
                    test = ensure_digest_schema_version(p)
                elif kind == "delta_request":
                    test = sanitize_delta_request(p)
                elif kind == "rebalance_decision":
                    test = sanitize_rebalance_decision_payload(p)
                elif kind == "evolution_sources":
                    test = normalize_evolution_sources_payload(p)
                elif kind == "evolution_proposals":
                    test = sanitize_evolution_proposals_payload(p)
                else:
                    test = p
                errs = validate_payload(kind, test)
            elif kind == "legacy_digest_markdown_only":
                fixed, e2 = digest_payload_from_daily_snapshots(str(row.get("date") or "")[:10])
                errs = [] if fixed is not None else (e2 or ["cannot rebuild digest from daily_snapshots"])
            elif kind.startswith("legacy_"):
                np, merrs = migrate_row(row)
                errs = merrs if np is None else []
            else:
                errs = ["unclassified"]
        else:
            errs = ["non-object payload"]
        report.append(
            {
                "id": pk,
                "date": row.get("date"),
                "document_key": dk,
                "kind": kind,
                "ok": len(errs) == 0,
                "errors": errs[:3],
            }
        )
    bad = [r for r in report if not r["ok"]]
    print(f"Audited {len(report)} documents; {len(bad)} with issues")
    if args.json:
        print(json.dumps({"documents": report}, indent=2))
    else:
        for r in bad[:50]:
            print(f"  ❌ {r['date']} {r['document_key']} [{r['kind']}]: {r['errors']}")
        if len(bad) > 50:
            print(f"  … and {len(bad) - 50} more (use --json)")
    return 0 if not bad else 1


def cmd_migrate(args: argparse.Namespace) -> int:
    sb = _sb()
    rows = fetch_all_documents(sb, args.only_key)
    dry = bool(args.dry_run)
    changed = 0
    for row in rows:
        np, errs = migrate_row(row)
        if np is None:
            continue
        meta = metadata_updates(str(row.get("document_key")), np)
        if dry:
            print(f"would update {row.get('date')} {row.get('document_key')} segment={meta.get('segment')}")
            changed += 1
            continue
        upd: Dict[str, Any] = {"payload": np, "segment": meta.get("segment")}
        if "doc_type" in meta:
            upd["doc_type"] = meta["doc_type"]
        if str(row.get("document_key") or "") == "digest" and _is_digest_snapshot(np):
            rendered = _render_digest_markdown_optional(np)
            if rendered:
                upd["content"] = rendered
        sb.table("documents").update(upd).eq("id", row["id"]).execute()
        print(f"✅ updated {row.get('date')} {row.get('document_key')}")
        changed += 1
    print(f"Done. {'Would change' if dry else 'Changed'} {changed} row(s).")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit / normalize Supabase documents payloads")
    sub = ap.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("audit")
    a.add_argument("--json", action="store_true")
    a.add_argument("--only-key", default=None, help="substring filter on document_key")
    a.set_defaults(func=cmd_audit)

    m = sub.add_parser("migrate")
    g = m.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true", dest="dry_run")
    g.add_argument("--apply", action="store_true", dest="apply")
    m.add_argument("--only-key", default=None)
    m.set_defaults(func=cmd_migrate, dry_run=False, apply=False)

    args = ap.parse_args()
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
