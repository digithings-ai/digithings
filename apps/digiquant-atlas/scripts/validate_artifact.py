#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

try:
    import jsonschema  # type: ignore

    _HAS_JSONSCHEMA = True
except ImportError:
    _HAS_JSONSCHEMA = False

ROOT = Path(__file__).resolve().parent.parent
SCHEMAS_DIR = ROOT / "templates" / "schemas"


def _load_json(path: Path) -> dict:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("artifact must be a JSON object")
    return data


def _load_payload_from_stdin() -> dict:
    raw = sys.stdin.read()
    if not raw.strip():
        raise ValueError("stdin is empty (pass JSON to validate)")
    data = json.loads(raw)
    if not isinstance(data, dict):
        raise ValueError("artifact must be a JSON object")
    return data


def _schema_path_for(doc_type: str) -> Path:
    mapping = {
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
        "pipeline_review": "pipeline-review.schema.json",
    }
    fname = mapping.get(doc_type)
    if not fname:
        raise ValueError(f"Unknown doc_type: {doc_type}")
    return SCHEMAS_DIR / fname


def _validate_digest_snapshot(payload: dict, label: str) -> int:
    schema = _load_json(ROOT / "templates" / "digest-snapshot-schema.json")
    jsonschema.validate(instance=payload, schema=schema)
    print(f"✅ valid: {label} (digest snapshot)")
    return 0


def _validate_delta_request(payload: dict, label: str) -> int:
    schema = _load_json(ROOT / "templates" / "delta-request-schema.json")
    jsonschema.validate(instance=payload, schema=schema)
    print(f"✅ valid: {label} (delta request)")
    return 0


def _infer_and_validate_payload(payload: dict, label: str) -> int:
    name_hint = ""
    if label != "<stdin>":
        name_hint = Path(label).name

    if name_hint == "_meta.json":
        print(f"⏭️  skip validation: {label}")
        return 0

    if name_hint == "snapshot.json":
        return _validate_digest_snapshot(payload, label)

    if name_hint == "delta-request.json":
        return _validate_delta_request(payload, label)

    doc_type = str(payload.get("doc_type") or "")
    if doc_type:
        schema_path = _schema_path_for(doc_type)
        schema = _load_json(schema_path)
        jsonschema.validate(instance=payload, schema=schema)
        print(f"✅ valid: {label} ({doc_type})")
        return 0

    if isinstance(payload.get("ops"), list) and isinstance(payload.get("changed_paths"), list):
        return _validate_delta_request(payload, label)

    if (
        "segment_biases" in payload
        and "sector_scorecard" in payload
        and "narrative" in payload
        and payload.get("run_type") in ("baseline", "delta")
    ):
        return _validate_digest_snapshot(payload, label)

    raise ValueError(
        "Could not infer artifact type: add doc_type to JSON, use a path named snapshot.json / "
        "delta-request.json, or pass a known schema shape (see templates/schemas/)."
    )


def main() -> int:
    ap = argparse.ArgumentParser(
        description="Validate a JSON artifact against its schema. Use '-' to read JSON from stdin."
    )
    ap.add_argument(
        "artifact",
        help="Path to JSON artifact file, or '-' for stdin (no repo-local path required).",
    )
    args = ap.parse_args()

    if not _HAS_JSONSCHEMA:
        print("jsonschema not installed. Run: pip install jsonschema", file=sys.stderr)
        return 2

    if args.artifact == "-":
        payload = _load_payload_from_stdin()
        return _infer_and_validate_payload(payload, "<stdin>")

    artifact_path = Path(args.artifact)
    payload = _load_json(artifact_path)
    return _infer_and_validate_payload(payload, str(artifact_path))


if __name__ == "__main__":
    sys.exit(main())
