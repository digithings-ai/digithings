# scripts/provider_review/bootstrap.py
"""Step 2 of provider review: assemble the Claude agent's context package.

Reads current snapshots, probe results, LiteLLM upstream pricing JSON,
and all # llm-decision: comment blocks from project config files.
Writes everything to /tmp/review/ for the agent to consume.

Usage:
    python scripts/provider_review/bootstrap.py
"""
from __future__ import annotations

import datetime
import json
from pathlib import Path

import httpx
import yaml

SNAPSHOTS_DIR = Path("docs/providers/snapshots")
LITELLM_PRICING_URL = (
    "https://raw.githubusercontent.com/BerriAI/litellm/main/"
    "model_prices_and_context_window.json"
)
DECISION_SCAN_PATHS = [
    "config/model_modes.yaml",
    "config/litellm.yaml",
    "digiquant/src/digiquant/atlas/config",
    "digiquant/src/digiquant/hermes/config",
]
_DECISION_LOOKAHEAD = 5  # lines scanned after tag to find the model assignment


def _json_default(obj: object) -> str:
    if isinstance(obj, (datetime.date, datetime.datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def load_snapshots() -> dict:
    """Return {stem: parsed_yaml} for all files in SNAPSHOTS_DIR."""
    return {
        p.stem: yaml.safe_load(p.read_text())
        for p in sorted(SNAPSHOTS_DIR.glob("*.yaml"))
    }


def fetch_litellm_pricing() -> dict:
    """Fetch LiteLLM's upstream model pricing JSON."""
    r = httpx.get(LITELLM_PRICING_URL, timeout=30, follow_redirects=True)
    r.raise_for_status()
    return r.json()


def extract_decision_comments(scan_paths: list[str]) -> list[dict]:
    """Grep all YAML files under scan_paths for # llm-decision: tags."""
    decisions: list[dict] = []
    for raw in scan_paths:
        path = Path(raw)
        if not path.exists():
            continue
        files = [path] if path.is_file() else sorted(path.rglob("*.yaml"))
        for yaml_file in files:
            lines = yaml_file.read_text().splitlines()
            for i, line in enumerate(lines):
                if line.strip().startswith("# llm-decision:"):
                    tags = line.strip().removeprefix("# llm-decision:").split()
                    # Collect optional prose line immediately after
                    prose = ""
                    if i + 1 < len(lines):
                        nxt = lines[i + 1].strip()
                        if nxt.startswith("#") and not nxt.startswith("# llm-decision:"):
                            prose = nxt.removeprefix("#").strip()
                    # Find the next non-comment YAML value (the model assignment)
                    model = None
                    for j in range(i + 1, min(i + 1 + _DECISION_LOOKAHEAD, len(lines))):
                        candidate = lines[j].strip()
                        if not candidate.startswith("#") and ":" in candidate:
                            model = candidate.split(":", 1)[1].strip().strip('"\'')
                            break
                    decisions.append({
                        "file": str(yaml_file),
                        "line": i + 1,
                        "tags": tags,
                        "prose": prose,
                        "model": model,
                    })
    return decisions


def assemble(
    probe_results_path: str = "/tmp/review/probe-results.json",
    output_dir: str = "/tmp/review",
) -> None:
    """Write all context files the Claude agent needs to /tmp/review/."""
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    snapshots = load_snapshots()
    (out / "snapshots.json").write_text(json.dumps(snapshots, indent=2, default=_json_default))
    print(f"  snapshots: {len(snapshots)} providers loaded")

    pricing = fetch_litellm_pricing()
    (out / "litellm-pricing.json").write_text(json.dumps(pricing, indent=2, default=_json_default))
    print(f"  litellm-pricing: {len(pricing)} models")

    decisions = extract_decision_comments(DECISION_SCAN_PATHS)
    (out / "decisions.json").write_text(json.dumps(decisions, indent=2, default=_json_default))
    print(f"  decisions: {len(decisions)} # llm-decision: entries found")

    probe_path = Path(probe_results_path)
    if probe_path.exists():
        (out / "probe-results.json").write_text(probe_path.read_text())
        print(f"  probe-results: loaded from {probe_results_path}")
    else:
        print(f"  probe-results: not found at {probe_results_path} — skipping")

    manifest = {
        "snapshot_count": len(snapshots),
        "pricing_model_count": len(pricing),
        "decision_count": len(decisions),
        "probe_results_available": probe_path.exists(),
    }
    (out / "manifest.json").write_text(json.dumps(manifest, indent=2))
    print(f"  manifest: {manifest}")


if __name__ == "__main__":
    print("Bootstrap: assembling context package...")
    assemble()
    print("Done — /tmp/review/ ready for agent.")
