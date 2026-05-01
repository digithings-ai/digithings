# Provider Review System — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build an automated weekly system that probes live LLM provider APIs, maintains machine-readable snapshots of 20 providers, evaluates model decisions across the project, and opens GitHub issues when quotas drop, models go paid-only, better free options appear, or paid costs increase materially.

**Architecture:** Four Python scripts handle probe, context assembly, and issue creation. A GitHub Actions workflow orchestrates them weekly, invoking a Claude agent for research and evaluation between the mechanical steps. Twenty YAML snapshot files in `docs/providers/snapshots/` serve as the machine-readable source of truth the agent diffs week-over-week.

**Tech Stack:** Python 3.12, `openai` SDK (OpenAI-compatible calls to all providers), `httpx`, `pyyaml`, GitHub Actions, Claude Code via `CLAUDE_CODE_OAUTH_TOKEN`, `gh` CLI.

**Spec:** `docs/superpowers/specs/2026-05-01-provider-review-design.md`

---

## File map

| Action | Path | Purpose |
|---|---|---|
| Create | `scripts/provider_review/__init__.py` | Makes module importable in tests |
| Create | `scripts/provider_review/probe.py` | Step 1: live probe all 9 providers |
| Create | `scripts/provider_review/bootstrap.py` | Step 2: assemble context package |
| Create | `scripts/provider_review/create_issues.py` | Step 4: deduplicate + open issues |
| Create | `tests/provider_review/__init__.py` | Test package marker |
| Create | `tests/provider_review/test_probe.py` | Unit tests for probe logic |
| Create | `tests/provider_review/test_bootstrap.py` | Unit tests for bootstrap logic |
| Create | `tests/provider_review/test_create_issues.py` | Unit tests for dedup logic |
| Create | `docs/providers/snapshots/gemini.yaml` | Gemini snapshot |
| Create | `docs/providers/snapshots/groq.yaml` | Groq snapshot |
| Create | `docs/providers/snapshots/cerebras.yaml` | Cerebras snapshot |
| Create | `docs/providers/snapshots/mistral.yaml` | Mistral snapshot |
| Create | `docs/providers/snapshots/nvidia_nim.yaml` | NVIDIA NIM snapshot |
| Create | `docs/providers/snapshots/ollama_cloud.yaml` | Ollama Cloud snapshot |
| Create | `docs/providers/snapshots/openrouter.yaml` | OpenRouter snapshot |
| Create | `docs/providers/snapshots/deepseek.yaml` | DeepSeek snapshot |
| Create | `docs/providers/snapshots/github_models.yaml` | GitHub Models snapshot |
| Create | `docs/providers/snapshots/xai.yaml` | xAI (Grok) snapshot — research-only |
| Create | `docs/providers/snapshots/openai.yaml` | OpenAI snapshot — research-only |
| Create | `docs/providers/snapshots/anthropic.yaml` | Anthropic snapshot — research-only |
| Create | `docs/providers/snapshots/cohere.yaml` | Cohere snapshot — research-only |
| Create | `docs/providers/snapshots/fireworks.yaml` | Fireworks snapshot — research-only |
| Create | `docs/providers/snapshots/together.yaml` | Together AI snapshot — research-only |
| Create | `docs/providers/snapshots/deepinfra.yaml` | DeepInfra snapshot — research-only |
| Create | `docs/providers/snapshots/perplexity.yaml` | Perplexity snapshot — research-only |
| Create | `docs/providers/snapshots/cloudflare.yaml` | Cloudflare Workers AI snapshot — research-only |
| Create | `docs/providers/snapshots/sambanova.yaml` | SambaNova snapshot — research-only |
| Create | `docs/providers/snapshots/huggingface.yaml` | HuggingFace snapshot — research-only |
| Create | `.github/workflows/provider-review.yml` | Weekly workflow |
| Modify | `config/model_modes.yaml` | Add `# llm-decision:` tags |

---

## Task 1: Project scaffold

**Files:**
- Create: `scripts/provider_review/__init__.py`
- Create: `tests/provider_review/__init__.py`

- [ ] **Step 1: Create the package directories and markers**

```bash
mkdir -p scripts/provider_review tests/provider_review
touch scripts/provider_review/__init__.py tests/provider_review/__init__.py
```

- [ ] **Step 2: Verify pytest can discover the test directory**

```bash
pytest tests/provider_review/ --collect-only
```

Expected: `no tests ran` (no test files yet, but no import errors either).

- [ ] **Step 3: Commit**

```bash
git add scripts/provider_review/__init__.py tests/provider_review/__init__.py
git commit -m "feat(provider-review): scaffold package directories"
```

---

## Task 2: probe.py

Live-probes each of the 9 providers using `openai.OpenAI` with provider-specific `base_url`. Follows the pattern established in `scripts/validate-provider-keys.py`.

**Files:**
- Create: `scripts/provider_review/probe.py`
- Create: `tests/provider_review/test_probe.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/provider_review/test_probe.py
"""Unit tests for scripts/provider_review/probe.py."""
from __future__ import annotations

import json
import os
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from scripts.provider_review.probe import PROVIDERS, probe_provider, run_probes


@pytest.mark.unit
def test_probe_provider_skipped_when_key_missing():
    """Returns skipped when the API key env var is absent."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "MISSING_KEY_XYZ_99",
        "model": "test-model",
    }
    result = probe_provider("test", config)
    assert result["status"] == "skipped"
    assert result["latency_ms"] is None
    assert result["error"] is None
    assert "MISSING_KEY_XYZ_99" in result["reason"]


@pytest.mark.unit
def test_probe_provider_ok_on_success():
    """Returns ok status and non-null latency on a successful call."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "FAKE_KEY_ABC",
        "model": "test-model",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.return_value = MagicMock()
    with patch.dict(os.environ, {"FAKE_KEY_ABC": "sk-test"}):
        with patch("scripts.provider_review.probe.OpenAI", return_value=mock_client):
            result = probe_provider("test", config)
    assert result["status"] == "ok"
    assert isinstance(result["latency_ms"], int)
    assert result["error"] is None


@pytest.mark.unit
def test_probe_provider_failed_on_exception():
    """Returns failed status with error message when the call raises."""
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "FAKE_KEY_ABC",
        "model": "test-model",
    }
    mock_client = MagicMock()
    mock_client.chat.completions.create.side_effect = Exception("401 Unauthorized")
    with patch.dict(os.environ, {"FAKE_KEY_ABC": "sk-test"}):
        with patch("scripts.provider_review.probe.OpenAI", return_value=mock_client):
            result = probe_provider("test", config)
    assert result["status"] == "failed"
    assert "401 Unauthorized" in result["error"]
    assert isinstance(result["latency_ms"], int)


@pytest.mark.unit
def test_run_probes_writes_json(tmp_path):
    """run_probes writes a JSON array to the output path."""
    output = tmp_path / "probe-results.json"
    config = {
        "base_url": "https://example.com/v1",
        "api_key_env": "MISSING_KEY_XYZ_99",
        "model": "test-model",
    }
    with patch("scripts.provider_review.probe.PROVIDERS", {"test": config}):
        results = run_probes(str(output))
    assert output.exists()
    data = json.loads(output.read_text())
    assert isinstance(data, list)
    assert data[0]["provider"] == "test"
    assert data[0]["status"] == "skipped"


@pytest.mark.unit
def test_providers_dict_has_nine_entries():
    """PROVIDERS covers exactly the 9 probeable providers."""
    assert len(PROVIDERS) == 9
    expected = {
        "gemini", "groq", "cerebras", "mistral", "nvidia_nim",
        "ollama_cloud", "openrouter", "deepseek", "github_models",
    }
    assert set(PROVIDERS.keys()) == expected
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/provider_review/test_probe.py -m unit -v
```

Expected: `ImportError` — `scripts.provider_review.probe` doesn't exist yet.

- [ ] **Step 3: Write probe.py**

```python
# scripts/provider_review/probe.py
"""Step 1 of provider review: live-probe each configured provider.

Sends a minimal prompt via the OpenAI-compatible API using each provider's
base_url and the corresponding GitHub secret. Records success/failure/latency.

Usage:
    python scripts/provider_review/probe.py
    # writes /tmp/review/probe-results.json
"""
from __future__ import annotations

import json
import os
import time
from datetime import datetime, timezone
from pathlib import Path

from openai import OpenAI

PROBE_PROMPT = "Reply with the single word: ok"
PROBE_MAX_TOKENS = 10
PROBE_TIMEOUT = 30

# Base URLs and credentials for each probeable provider.
# api_key_env: the GitHub org secret that holds the key.
PROVIDERS: dict[str, dict] = {
    "gemini": {
        "base_url": "https://generativelanguage.googleapis.com/v1beta/openai/",
        "api_key_env": "GEMINI_API_KEY",
        "model": "gemini-2.5-flash",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "api_key_env": "GROQ_API_KEY",
        "model": "llama-3.3-70b-versatile",
    },
    "cerebras": {
        "base_url": "https://api.cerebras.ai/v1",
        "api_key_env": "CEREBRAS_API_KEY",
        "model": "llama-3.3-70b",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "api_key_env": "MISTRAL_API_KEY",
        "model": "mistral-small-latest",
    },
    "nvidia_nim": {
        "base_url": "https://integrate.api.nvidia.com/v1",
        "api_key_env": "NVIDIA_API_KEY",
        "model": "meta/llama-3.3-70b-instruct",
    },
    "ollama_cloud": {
        "base_url": "https://ollama.com/v1",
        "api_key_env": "OLLAMA_API_KEY",
        "model": "rnj-1:cloud",
    },
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key_env": "OPENROUTER_API_KEY",
        "model": "meta-llama/llama-3.3-70b-instruct:free",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "api_key_env": "DEEPSEEK_API_KEY",
        "model": "deepseek-chat",
    },
    "github_models": {
        "base_url": "https://models.inference.ai.azure.com",
        "api_key_env": "GITHUB_TOKEN",
        "model": "gpt-4o-mini",
    },
}


def probe_provider(name: str, config: dict) -> dict:
    """Probe a single provider. Returns a result dict; never raises."""
    api_key = os.environ.get(config["api_key_env"], "").strip()
    probed_at = datetime.now(timezone.utc).isoformat()

    if not api_key:
        return {
            "provider": name,
            "status": "skipped",
            "reason": f"{config['api_key_env']} not set",
            "latency_ms": None,
            "error": None,
            "probed_at": probed_at,
        }

    client = OpenAI(api_key=api_key, base_url=config["base_url"])
    start = time.monotonic()
    try:
        client.chat.completions.create(
            model=config["model"],
            messages=[{"role": "user", "content": PROBE_PROMPT}],
            max_tokens=PROBE_MAX_TOKENS,
            timeout=PROBE_TIMEOUT,
        )
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "provider": name,
            "status": "ok",
            "reason": None,
            "latency_ms": latency_ms,
            "error": None,
            "probed_at": probed_at,
        }
    except Exception as exc:
        latency_ms = round((time.monotonic() - start) * 1000)
        return {
            "provider": name,
            "status": "failed",
            "reason": None,
            "latency_ms": latency_ms,
            "error": str(exc),
            "probed_at": probed_at,
        }


def run_probes(output_path: str = "/tmp/review/probe-results.json") -> list[dict]:
    """Probe all providers and write results JSON. Always exits 0."""
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    results = [probe_provider(name, cfg) for name, cfg in PROVIDERS.items()]
    Path(output_path).write_text(json.dumps(results, indent=2))
    return results


if __name__ == "__main__":
    results = run_probes()
    for r in results:
        status = r["status"].upper()
        latency = f"{r['latency_ms']}ms" if r["latency_ms"] is not None else "—"
        suffix = f" ({r['error'][:80]})" if r.get("error") else (f" — {r['reason']}" if r.get("reason") else "")
        print(f"  {status:7} {r['provider']:<15} {latency}{suffix}")
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/provider_review/test_probe.py -m unit -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/provider_review/probe.py tests/provider_review/test_probe.py
git commit -m "feat(provider-review): add probe.py with unit tests"
```

---

## Task 3: bootstrap.py

Assembles the context package for the Claude agent: current snapshots, probe results, LiteLLM upstream pricing JSON, and extracted `# llm-decision:` comment blocks from all project config files.

**Files:**
- Create: `scripts/provider_review/bootstrap.py`
- Create: `tests/provider_review/test_bootstrap.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/provider_review/test_bootstrap.py
"""Unit tests for scripts/provider_review/bootstrap.py."""
from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from scripts.provider_review.bootstrap import extract_decision_comments, load_snapshots


@pytest.mark.unit
def test_extract_finds_tagged_entry(tmp_path):
    """Finds a # llm-decision: tag and captures tags, prose, and model."""
    cfg = tmp_path / "model_modes.yaml"
    cfg.write_text(
        "phase_models:\n"
        "  # llm-decision: reasoning free-preferred\n"
        "  # DeepSeek chosen for math benchmark strength on free tier\n"
        "  master-digest: \"ollama-cloud/deepseek-v3.1:671b\"\n"
    )
    decisions = extract_decision_comments([str(cfg)])
    assert len(decisions) == 1
    d = decisions[0]
    assert d["tags"] == ["reasoning", "free-preferred"]
    assert "DeepSeek" in d["prose"]
    assert "deepseek-v3.1:671b" in d["model"]
    assert d["line"] == 2


@pytest.mark.unit
def test_extract_empty_when_no_tags(tmp_path):
    """Returns empty list when no # llm-decision: tags are present."""
    cfg = tmp_path / "config.yaml"
    cfg.write_text("model: gemini/gemini-2.5-flash\n")
    assert extract_decision_comments([str(cfg)]) == []


@pytest.mark.unit
def test_extract_skips_missing_paths(tmp_path):
    """Silently skips paths that do not exist."""
    assert extract_decision_comments([str(tmp_path / "ghost.yaml")]) == []


@pytest.mark.unit
def test_extract_scans_directory_recursively(tmp_path):
    """When given a directory path, finds tags in all nested YAML files."""
    sub = tmp_path / "sub"
    sub.mkdir()
    (sub / "a.yaml").write_text(
        "# llm-decision: extraction free-preferred\n"
        "model: gemini/gemini-2.5-flash\n"
    )
    (sub / "b.yaml").write_text("model: gemini/gemini-2.5-flash\n")
    decisions = extract_decision_comments([str(tmp_path)])
    assert len(decisions) == 1
    assert decisions[0]["tags"] == ["extraction", "free-preferred"]


@pytest.mark.unit
def test_load_snapshots_reads_all_yaml(tmp_path):
    """Loads all .yaml files from the snapshots directory."""
    (tmp_path / "gemini.yaml").write_text("provider: gemini\nlast_checked: 2026-05-01\n")
    (tmp_path / "groq.yaml").write_text("provider: groq\nlast_checked: 2026-05-01\n")
    with patch("scripts.provider_review.bootstrap.SNAPSHOTS_DIR", tmp_path):
        snapshots = load_snapshots()
    assert set(snapshots.keys()) == {"gemini", "groq"}
    assert snapshots["gemini"]["provider"] == "gemini"
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/provider_review/test_bootstrap.py -m unit -v
```

Expected: `ImportError` — `scripts.provider_review.bootstrap` doesn't exist yet.

- [ ] **Step 3: Write bootstrap.py**

```python
# scripts/provider_review/bootstrap.py
"""Step 2 of provider review: assemble the Claude agent's context package.

Reads current snapshots, probe results, LiteLLM upstream pricing JSON,
and all # llm-decision: comment blocks from project config files.
Writes everything to /tmp/review/ for the agent to consume.

Usage:
    python scripts/provider_review/bootstrap.py
"""
from __future__ import annotations

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
                            prose = nxt.lstrip("# ").strip()
                    # Find the next non-comment YAML value (the model assignment)
                    model = None
                    for j in range(i + 1, min(i + 6, len(lines))):
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
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    snapshots = load_snapshots()
    (out / "snapshots.json").write_text(json.dumps(snapshots, indent=2))
    print(f"  snapshots: {len(snapshots)} providers loaded")

    pricing = fetch_litellm_pricing()
    (out / "litellm-pricing.json").write_text(json.dumps(pricing, indent=2))
    print(f"  litellm-pricing: {len(pricing)} models")

    decisions = extract_decision_comments(DECISION_SCAN_PATHS)
    (out / "decisions.json").write_text(json.dumps(decisions, indent=2))
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
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/provider_review/test_bootstrap.py -m unit -v
```

Expected: 5 tests pass.

- [ ] **Step 5: Commit**

```bash
git add scripts/provider_review/bootstrap.py tests/provider_review/test_bootstrap.py
git commit -m "feat(provider-review): add bootstrap.py with unit tests"
```

---

## Task 4: create_issues.py

Reads the agent's `findings.json`, deduplicates against open `provider-review` issues, and opens one focused issue per novel finding.

**Files:**
- Create: `scripts/provider_review/create_issues.py`
- Create: `tests/provider_review/test_create_issues.py`

- [ ] **Step 1: Write the failing tests**

```python
# tests/provider_review/test_create_issues.py
"""Unit tests for scripts/provider_review/create_issues.py."""
from __future__ import annotations

import pytest

from scripts.provider_review.create_issues import DEDUP_KEY_FORMAT, is_duplicate


@pytest.mark.unit
def test_is_duplicate_same_provider_trigger():
    """Returns True when an open issue body contains the same dedup key."""
    finding = {"provider": "gemini", "trigger": "quota_drop"}
    key = DEDUP_KEY_FORMAT.format(**finding)
    open_issues = [{"number": 1, "title": "...", "body": f"<!-- dedup-key: {key} -->"}]
    assert is_duplicate(finding, open_issues) is True


@pytest.mark.unit
def test_is_duplicate_different_trigger():
    """Returns False when same provider has a different trigger in open issues."""
    finding = {"provider": "gemini", "trigger": "better_free"}
    open_issues = [
        {"number": 1, "title": "...", "body": "<!-- dedup-key: gemini:quota_drop -->"}
    ]
    assert is_duplicate(finding, open_issues) is False


@pytest.mark.unit
def test_is_duplicate_no_open_issues():
    """Returns False when there are no open issues at all."""
    finding = {"provider": "groq", "trigger": "model_deprecated"}
    assert is_duplicate(finding, []) is False


@pytest.mark.unit
def test_is_duplicate_none_body():
    """Returns False when an open issue has a None body (edge case)."""
    finding = {"provider": "gemini", "trigger": "quota_drop"}
    open_issues = [{"number": 1, "title": "...", "body": None}]
    assert is_duplicate(finding, open_issues) is False
```

- [ ] **Step 2: Run to verify tests fail**

```bash
pytest tests/provider_review/test_create_issues.py -m unit -v
```

Expected: `ImportError` — module doesn't exist yet.

- [ ] **Step 3: Write create_issues.py**

```python
# scripts/provider_review/create_issues.py
"""Step 4 of provider review: open GitHub issues for each novel finding.

Reads /tmp/review/findings.json (written by the Claude agent in Step 3),
deduplicates against open issues tagged provider-review, and creates one
issue per novel finding.

Usage:
    REPO=digithings-ai/digithings GH_TOKEN=... python scripts/provider_review/create_issues.py
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

FINDINGS_PATH = "/tmp/review/findings.json"
LABEL = "provider-review"
ISSUE_LABELS = "exec:claude,component:root,type:research,priority:medium,risk:low,provider-review"
MARKER = "<!-- provider-review -->"
DEDUP_KEY_FORMAT = "{provider}:{trigger}"


def ensure_label(repo: str) -> None:
    """Create the provider-review label if it doesn't exist."""
    result = subprocess.run(
        ["gh", "label", "list", "--repo", repo, "--json", "name"],
        capture_output=True, text=True, check=True,
    )
    existing = {item["name"] for item in json.loads(result.stdout or "[]")}
    if LABEL not in existing:
        subprocess.run(
            ["gh", "label", "create", LABEL, "--repo", repo,
             "--color", "0075ca",
             "--description", "Automated provider review finding"],
            check=True,
        )
        print(f"  Created label: {LABEL}")


def get_open_provider_issues(repo: str) -> list[dict]:
    """Fetch all open issues tagged provider-review."""
    result = subprocess.run(
        ["gh", "issue", "list", "--repo", repo, "--label", LABEL,
         "--state", "open", "--json", "number,title,body", "--limit", "100"],
        capture_output=True, text=True, check=True,
    )
    return json.loads(result.stdout or "[]")


def is_duplicate(finding: dict, open_issues: list[dict]) -> bool:
    """Return True if an open issue already covers this provider:trigger pair."""
    key = DEDUP_KEY_FORMAT.format(**finding)
    needle = f"<!-- dedup-key: {key} -->"
    return any(needle in (issue.get("body") or "") for issue in open_issues)


def build_body(finding: dict) -> str:
    key = DEDUP_KEY_FORMAT.format(**finding)
    tags_str = " ".join(finding.get("tags", []))
    return f"""{MARKER}
<!-- dedup-key: {key} -->
## Provider change detected: {finding['provider']} — {finding['summary']}

**Trigger:** {finding['trigger']}
**Affected config:** `{finding.get('config_file', 'N/A')}` (`# llm-decision: {tags_str}`)
**Current model:** `{finding.get('current_model', 'N/A')}`
**Finding:** {finding['detail']}

### Cost-benefit assessment
{finding.get('cost_benefit_table', '_Agent assessment not available_')}

**Recommendation:** {finding.get('recommendation', 'Review and update the affected config entry.')}

### Next steps
- [ ] Review the affected config entry
- [ ] Run `make task ISSUE=<N>` to execute the update
"""


def run(findings_path: str = FINDINGS_PATH) -> None:
    repo = os.environ.get("REPO", "").strip()
    if not repo:
        print("REPO env var not set", file=sys.stderr)
        sys.exit(1)

    if not Path(findings_path).exists():
        print(f"No findings file at {findings_path} — nothing to do.")
        return

    findings = json.loads(Path(findings_path).read_text())
    if not findings:
        print("findings.json is empty — no issues to create.")
        return

    ensure_label(repo)
    open_issues = get_open_provider_issues(repo)
    print(f"  {len(open_issues)} open provider-review issues (for dedup)")

    created = skipped = 0
    for finding in findings:
        if is_duplicate(finding, open_issues):
            print(f"  SKIP  {finding['provider']}:{finding['trigger']} — already open")
            skipped += 1
            continue

        title = f"[provider-review] {finding['provider']}: {finding['summary']}"
        body = build_body(finding)
        result = subprocess.run(
            ["gh", "issue", "create", "--repo", repo,
             "--title", title, "--label", ISSUE_LABELS, "--body", body],
            capture_output=True, text=True, check=True,
        )
        url = result.stdout.strip()
        print(f"  CREATE {finding['provider']}:{finding['trigger']} → {url}")
        created += 1

    print(f"\nDone — {created} created, {skipped} skipped.")


if __name__ == "__main__":
    run()
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/provider_review/test_create_issues.py -m unit -v
```

Expected: 4 tests pass.

- [ ] **Step 5: Run all provider-review unit tests together**

```bash
pytest tests/provider_review/ -m unit -v
```

Expected: 14 tests pass total.

- [ ] **Step 6: Commit**

```bash
git add scripts/provider_review/create_issues.py tests/provider_review/test_create_issues.py
git commit -m "feat(provider-review): add create_issues.py with unit tests"
```

---

## Task 5: Seed probeable provider snapshots (9 files)

Create `docs/providers/snapshots/` with initial YAML data for every provider where we have a key. The Claude agent will update these on its first run; these seeds give it a baseline to diff against.

**Files:**
- Create: `docs/providers/snapshots/gemini.yaml`
- Create: `docs/providers/snapshots/groq.yaml`
- Create: `docs/providers/snapshots/cerebras.yaml`
- Create: `docs/providers/snapshots/mistral.yaml`
- Create: `docs/providers/snapshots/nvidia_nim.yaml`
- Create: `docs/providers/snapshots/ollama_cloud.yaml`
- Create: `docs/providers/snapshots/openrouter.yaml`
- Create: `docs/providers/snapshots/deepseek.yaml`
- Create: `docs/providers/snapshots/github_models.yaml`

- [ ] **Step 1: Create the snapshots directory**

```bash
mkdir -p docs/providers/snapshots
```

- [ ] **Step 2: Write docs/providers/snapshots/gemini.yaml**

```yaml
provider: gemini
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: "Free-tier prompts/responses used to improve Google products. Never send confidential data."
  signup_required: false
  cc_required: false
  models:
    - name: gemini-2.5-flash
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: gemini-2.5-flash-lite
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: gemini-2.5-pro
      context_window: 2097152
      max_input_tokens: 2097152
      max_output_tokens: 65536
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: text-embedding-004
      context_window: 2048
      max_input_tokens: 2048
      max_output_tokens: null
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 10              # Flash; Flash-Lite is 15, Pro is 5
    rpd: 250             # Flash; Flash-Lite is 1000, Pro is 100
    tpm: 250000          # Flash; Flash-Lite is 1000000, Pro is 250000
    input_tpm: null
    concurrent_requests: null
    reset_window: calendar_day

paid_tier:
  available: true
  models:
    - name: gemini-2.5-flash
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      cost_per_1m_input: 0.30
      cost_per_1m_input_long: null
      cost_per_1m_output: 2.50
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.075
      status: active
    - name: gemini-2.5-flash-lite
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      cost_per_1m_input: 0.10
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.40
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: gemini-2.5-pro
      context_window: 2097152
      max_input_tokens: 2097152
      max_output_tokens: 65536
      cost_per_1m_input: 1.25
      cost_per_1m_input_long: 2.50   # >200k tokens
      cost_per_1m_output: 10.00
      cost_per_1m_output_long: 15.00
      cost_per_1m_input_cached: 0.31
      status: active
  batching:
    available: true
    discount_pct: 50
    max_batch_size: null
    turnaround_hours: 24
    notes: "Async batch API; results via polling"
  prompt_caching:
    available: true
    min_cacheable_tokens: 1024
    ttl_seconds: 3600
    cost_per_1m_cached_writes: 0.375
    cost_per_1m_cached_reads: 0.075
    notes: "Cache writes billed once; reads at ~75% discount"

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true
  streaming: true
  vision: true
  embeddings: true
  modalities: [text, image, audio, video]

data_privacy:
  trains_on_free_tier: true
  retention_days: null
  zero_retention_on_paid: true
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: gemini-flash
  github_secret_key: GEMINI_API_KEY

notes: "Paid tier: same API key, enable billing on Google Cloud project. Zero-retention on paid."
```

- [ ] **Step 3: Write docs/providers/snapshots/groq.yaml**

```yaml
provider: groq
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: false
  cc_required: false
  models:
    - name: llama-3.3-70b-versatile
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 32768
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: llama-4-scout-17b-16e-instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: moonshotai/kimi-k2-instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek-r1-distill-llama-70b
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 30
    rpd: 14400
    tpm: 6000            # llama-3.3-70b-versatile; varies 6k-30k by model
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_24h

paid_tier:
  available: true
  models:
    - name: llama-3.3-70b-versatile
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 32768
      cost_per_1m_input: 0.59
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.79
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: llama-4-scout-17b-16e-instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      cost_per_1m_input: 0.11
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.34
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: true   # TPM limits too low for Atlas pipeline (6k vs 41k needed)
  requires_backoff: true
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: groq-llama-70b
  github_secret_key: GROQ_API_KEY

notes: "TPM 6k on llama-3.3-70b-versatile makes it unsuitable for Atlas extraction (needs 41k). Inference is 500-1500 tok/s — fastest free option if TPM is not a constraint."
```

- [ ] **Step 4: Write docs/providers/snapshots/cerebras.yaml**

```yaml
provider: cerebras
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: false
  cc_required: false
  models:
    - name: llama-3.3-70b
      context_window: 128000
      max_input_tokens: 8192    # often capped below native on free tier
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: llama-4-scout
      context_window: 131072
      max_input_tokens: 8192
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: qwen-3-32b
      context_window: 32768
      max_input_tokens: 8192
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 30
    rpd: 60
    tpm: null              # ~1M tokens/day total; per-minute not published
    input_tpm: null
    concurrent_requests: null
    reset_window: calendar_day

paid_tier:
  available: true
  models:
    - name: llama-3.3-70b
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 32768
      cost_per_1m_input: 0.60
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.60
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: false

reliability:
  known_instability: false
  requires_backoff: true
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: cerebras-llama-70b
  github_secret_key: CEREBRAS_API_KEY

notes: "Fastest inference on market (>2000 tok/s). Context often capped at 8k on free — chunking required for large inputs. Paid tier unlocks full 128k."
```

- [ ] **Step 5: Write docs/providers/snapshots/mistral.yaml**

```yaml
provider: mistral
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: trial          # "Experimental" tier; phone verification required
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: "Free tier allows training on your data. Codestral commercial use requires paid."
  signup_required: true
  cc_required: false
  models:
    - name: mistral-large-latest
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 131072
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: mistral-small-latest
      context_window: 32768
      max_input_tokens: 32768
      max_output_tokens: 32768
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: codestral-latest
      context_window: 262144
      max_input_tokens: 262144
      max_output_tokens: 262144
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 60              # ~1 RPS
    rpd: null
    tpm: 500000
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_minute

paid_tier:
  available: true
  models:
    - name: mistral-large-latest
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 131072
      cost_per_1m_input: 2.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 6.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: mistral-small-latest
      context_window: 32768
      max_input_tokens: 32768
      max_output_tokens: 32768
      cost_per_1m_input: 0.20
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.60
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: codestral-latest
      context_window: 262144
      max_input_tokens: 262144
      max_output_tokens: 262144
      cost_per_1m_input: 0.30
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.90
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: true             # pixtral variants
  embeddings: true
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: true
  retention_days: null
  zero_retention_on_paid: true
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: true
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: mistral-small
  github_secret_key: MISTRAL_API_KEY

notes: "Experimental tier requires phone verification. Very high monthly token allowance (~1B/month reported). Add retry logic — 429s are common on bursts."
```

- [ ] **Step 6: Write docs/providers/snapshots/nvidia_nim.yaml**

```yaml
provider: nvidia_nim
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: credits
  credit_amount_usd: null      # 1000-5000 inference credits on signup; not USD-denominated
  credit_expiry_days: null     # credits do not expire but do not refill
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: meta/llama-3.3-70b-instruct
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 4096
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: nvidia/llama-3.3-nemotron-super-49b-v1
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 4096
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek-ai/deepseek-r1
      context_window: 163840
      max_input_tokens: 163840
      max_output_tokens: 32768
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 40
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_minute

paid_tier:
  available: true
  models: []              # Paid is usage-based on same models; pricing not published per-model
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # Nemotron reasoning models
  streaming: true
  vision: false
  embeddings: true
  modalities: [text]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: nvidia-llama-70b
  github_secret_key: NVIDIA_API_KEY

notes: "Credits do not refill — best for prototyping and evaluation, not heavy daily automation. 80+ optimized models available. Developer Program grants 5000 additional credits."
```

- [ ] **Step 7: Write docs/providers/snapshots/ollama_cloud.yaml**

```yaml
provider: ollama_cloud
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing        # Metered in GPU-seconds on rolling 5h / 7-day windows
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: rnj-1:cloud
      context_window: 32768
      max_input_tokens: 32768
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek-v3.1:671b
      context_window: 163840
      max_input_tokens: 163840
      max_output_tokens: 32768
      status: active          # confirmed free as of Apr 2026
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: cogito-2.1:671b
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 32768
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: nemotron-3-super:cloud
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 32768
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek-v4-flash
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 65536
      status: paid-only       # moved behind subscription Apr 2026
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: kimi-k2-thinking
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 32768
      status: paid-only       # moved behind subscription Apr 2026
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null               # rate-limited by GPU-seconds, not RPM
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: 1  # 1 concurrent model on free tier
    reset_window: rolling_24h

paid_tier:
  available: true
  models: []               # Same models; Pro $20/mo (50× free, 3 concurrent), Max $100/mo
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # cogito, deepseek-v3.1 have thinking modes
  streaming: true
  vision: true             # kimi-k2.6, gemma4, others
  embeddings: false
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false

reliability:
  known_instability: false
  requires_backoff: true
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: ollama-cloud/rnj-1
  github_secret_key: OLLAMA_API_KEY

notes: "OpenAI-compatible passthrough at https://ollama.com/v1. Uses OLLAMA_API_KEY. Subscription models (deepseek-v4-flash, kimi-k2-thinking, glm-5.1, kimi-k2.6, devstral-2) return 403 on free tier — probe will detect. deepseek-v3.1:671b is the recommended free reasoning-tier model."
```

- [ ] **Step 8: Write docs/providers/snapshots/openrouter.yaml**

```yaml
provider: openrouter
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: "Some :free model providers may log prompts — check each model card."
  signup_required: false
  cc_required: false
  models:
    - name: deepseek/deepseek-chat-v3:free
      context_window: 163840
      max_input_tokens: 163840
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek/deepseek-r1:free
      context_window: 163840
      max_input_tokens: 163840
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: meta-llama/llama-3.3-70b-instruct:free
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: google/gemini-2.0-flash-exp:free
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 20
    rpd: 50              # <$10 balance; 1000 RPD after adding $10+
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_24h

paid_tier:
  available: true
  models: []             # Aggregator: 0-5% markup over upstream; BYO-key (5% surcharge)
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # via :free R1 variants
  streaming: true
  vision: true             # via gemini-2.0-flash-exp:free
  embeddings: false
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: false  # OpenRouter itself doesn't train; upstream provider varies
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false

reliability:
  known_instability: false
  requires_backoff: true    # :free routes can queue during high traffic
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: openrouter-llama-70b-free
  github_secret_key: OPENROUTER_API_KEY

notes: ":free model roster rotates — verify current list at https://openrouter.ai/models?q=free. Adding $10 balance raises RPD from 50 to 1000 for all :free models."
```

- [ ] **Step 9: Write docs/providers/snapshots/deepseek.yaml**

```yaml
provider: deepseek
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: credits
  credit_amount_usd: null      # 5M tokens on signup (not USD-denominated)
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: deepseek-chat
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: deepseek-reasoner
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null            # dynamic; no hard published limit
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null

paid_tier:
  available: true
  models:
    - name: deepseek-chat
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      cost_per_1m_input: 0.27
      cost_per_1m_input_long: null
      cost_per_1m_output: 1.10
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.07
      status: active
    - name: deepseek-reasoner
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      cost_per_1m_input: 0.55
      cost_per_1m_input_long: null
      cost_per_1m_output: 2.19
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.14
      status: active
  batching:
    available: true
    discount_pct: 50
    max_batch_size: null
    turnaround_hours: 24
    notes: "Batch API available; 50% discount on asynchronous requests"
  prompt_caching:
    available: true
    min_cacheable_tokens: 1024
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: 0.07
    notes: "Cache hit reads at ~75% discount vs standard input price"

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # deepseek-reasoner (R1) has extended reasoning
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: deepseek-chat
  github_secret_key: DEEPSEEK_API_KEY

notes: "5M free tokens on signup (one-time). After that, cheapest frontier-class model available. Strong quantitative reasoning — excellent for Atlas extraction and research tiers at minimal cost."
```

- [ ] **Step 10: Write docs/providers/snapshots/github_models.yaml**

```yaml
provider: github_models
last_checked: 2026-05-01
source: manual

free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: "ToS restricts free tier to evaluation — not production use. Graduate to Azure AI for commercial workloads."
  signup_required: false
  cc_required: false
  models:
    - name: gpt-4o-mini
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: gpt-4o
      context_window: 128000
      max_input_tokens: 128000
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: meta-llama/Llama-3.3-70B-Instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 4096
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: mistral-large-2411
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 4096
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null            # varies by Copilot tier and model tier
    rpd: 50              # low-tier models; high-tier (GPT-4o) ~8 RPD on free
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: calendar_day

paid_tier:
  available: false       # production workloads route to Azure OpenAI, not GitHub Models
  models: []
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: true
  embeddings: true
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: litellm_probe
  probe_prompt: "Reply with the single word: ok"
  probe_model_alias: github-gpt4o-mini
  github_secret_key: GITHUB_TOKEN

notes: "GITHUB_TOKEN is always available in Actions — no extra secret needed. Daily RPD is very low; best used for the weekly agent run itself, not production routing."
```

- [ ] **Step 11: Commit all probeable provider snapshots**

```bash
git add docs/providers/snapshots/
git commit -m "feat(provider-review): seed initial snapshots for 9 probeable providers"
```

---

## Task 6: Seed research-only provider snapshots (11 files)

These providers have no API key yet. Full schema with known data; the agent will complete and refine on first run.

**Files:** `docs/providers/snapshots/{xai,openai,anthropic,cohere,fireworks,together,deepinfra,perplexity,cloudflare,sambanova,huggingface}.yaml`

- [ ] **Step 1: Write docs/providers/snapshots/xai.yaml**

```yaml
provider: xai
last_checked: 2026-05-01
source: agent-research

free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null

paid_tier:
  available: true
  models:
    - name: grok-4-1-fast
      context_window: 2097152
      max_input_tokens: 2097152
      max_output_tokens: null
      cost_per_1m_input: 0.20
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.50
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: grok-4-3
      context_window: 2097152
      max_input_tokens: 2097152
      max_output_tokens: null
      cost_per_1m_input: 3.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 15.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true
  streaming: true
  vision: true
  embeddings: false
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null

notes: "Grok-4.1-Fast offers 2M context at $0.20/$0.50 — best context/cost ratio for large document processing. Real-time X/Twitter data access adds market sentiment value. No key configured yet."
```

- [ ] **Step 2: Write docs/providers/snapshots/openai.yaml**

```yaml
provider: openai
last_checked: 2026-05-01
source: agent-research

free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null

paid_tier:
  available: true
  models:
    - name: gpt-4.1
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 32768
      cost_per_1m_input: 2.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 8.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.50
      status: active
    - name: gpt-4.1-mini
      context_window: 1048576
      max_input_tokens: 1048576
      max_output_tokens: 32768
      cost_per_1m_input: 0.15
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.60
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.075
      status: active
    - name: o3
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: 100000
      cost_per_1m_input: 2.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 8.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.50
      status: active
  batching:
    available: true
    discount_pct: 50
    max_batch_size: null
    turnaround_hours: 24
    notes: "Batch API; 50% discount on async requests"
  prompt_caching:
    available: true
    min_cacheable_tokens: 1024
    ttl_seconds: 3600
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: 0.50
    notes: "Automatic caching for repeated prompt prefixes"

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # o3 series
  streaming: true
  vision: true
  embeddings: true
  modalities: [text, image, audio]

data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: true  # with zero-data-retention add-on
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null

notes: "GPT-4.1-mini at $0.15/$0.60 is extremely competitive for extraction tier. Full 1M context on GPT-4.1 for large document analysis. No key configured yet."
```

- [ ] **Step 3: Write docs/providers/snapshots/anthropic.yaml**

```yaml
provider: anthropic
last_checked: 2026-05-01
source: agent-research

free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null

paid_tier:
  available: true
  models:
    - name: claude-haiku-4-5
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: 8192
      cost_per_1m_input: 1.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 5.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.30
      status: active
    - name: claude-sonnet-4-6
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: 64000
      cost_per_1m_input: 3.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 15.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 0.30
      status: active
    - name: claude-opus-4-7
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: 32000
      cost_per_1m_input: 5.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 25.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: 1.50
      status: active
  batching:
    available: true
    discount_pct: 50
    max_batch_size: 100000
    turnaround_hours: 24
    notes: "Message Batches API; up to 100k requests per batch"
  prompt_caching:
    available: true
    min_cacheable_tokens: 1024
    ttl_seconds: 300         # 5-minute default TTL
    cost_per_1m_cached_writes: 3.75
    cost_per_1m_cached_reads: 0.30
    notes: "Cache read at 90% discount vs standard input. Write cost is 25% premium."

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true      # extended thinking on Sonnet/Opus
  streaming: true
  vision: true
  embeddings: false
  modalities: [text, image]

data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null

notes: "Lowest hallucination rate on finance reasoning benchmarks. CLAUDE_CODE_OAUTH_TOKEN present but is for Claude Code CLI — not usable as LiteLLM API key. Needs separate ANTHROPIC_API_KEY."
```

- [ ] **Step 4: Write docs/providers/snapshots/cohere.yaml**

```yaml
provider: cohere
last_checked: 2026-05-01
source: agent-research

free_tier:
  available: true
  tier_type: trial
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: "Trial keys may not be used for commercial production."
  signup_required: true
  cc_required: false
  models:
    - name: command-a-03-2025
      context_window: 256000
      max_input_tokens: 256000
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 20
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_minute

paid_tier:
  available: true
  models:
    - name: command-a-03-2025
      context_window: 256000
      max_input_tokens: 256000
      max_output_tokens: 8192
      cost_per_1m_input: 2.50
      cost_per_1m_input_long: null
      cost_per_1m_output: 10.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null

capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: true       # embed-v3 — best-in-class for RAG
  modalities: [text]

data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true

reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []

verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null

notes: "256k context + best-in-class RAG embeddings. Trial tier is 1000 calls/month — too low for daily automation but good for evaluation. No key configured yet."
```

- [ ] **Step 5: Write remaining 7 research-only snapshots**

```bash
# Write docs/providers/snapshots/fireworks.yaml
cat > docs/providers/snapshots/fireworks.yaml << 'EOF'
provider: fireworks
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: true
  tier_type: credits
  credit_amount_usd: 1.00
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: accounts/fireworks/models/llama-v3p3-70b-instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: accounts/fireworks/models/deepseek-r1
      context_window: 163840
      max_input_tokens: 163840
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null
paid_tier:
  available: true
  models:
    - name: accounts/fireworks/models/llama-v3p3-70b-instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      cost_per_1m_input: 0.90
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.90
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: true
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]
data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: true
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "$1 starter credits. Fast open-weight inference, FireFunction for tool calling. No key configured yet."
EOF

# Write docs/providers/snapshots/together.yaml
cat > docs/providers/snapshots/together.yaml << 'EOF'
provider: together
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null
paid_tier:
  available: true
  models:
    - name: meta-llama/Llama-3.3-70B-Instruct-Turbo
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      cost_per_1m_input: 0.88
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.88
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: deepseek-ai/DeepSeek-V3
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      cost_per_1m_input: 1.25
      cost_per_1m_input_long: null
      cost_per_1m_output: 1.25
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: true
  modalities: [text]
data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: true
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "Open-weight models + fine-tuning. Competitive pricing for volume. No key configured yet."
EOF

# Write docs/providers/snapshots/deepinfra.yaml
cat > docs/providers/snapshots/deepinfra.yaml << 'EOF'
provider: deepinfra
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null
paid_tier:
  available: true
  models:
    - name: meta-llama/Llama-3.3-70B-Instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      cost_per_1m_input: 0.23
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.40
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: deepseek-ai/DeepSeek-V3
      context_window: 65536
      max_input_tokens: 65536
      max_output_tokens: 8192
      cost_per_1m_input: 0.49
      cost_per_1m_input_long: null
      cost_per_1m_output: 0.89
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: true
  structured_output: true
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: true
  modalities: [text]
data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "Cheapest open-weight hosting ($0.23/1M Llama 3.3 70B). Good for high-volume extraction tier. No key configured yet."
EOF

# Write docs/providers/snapshots/perplexity.yaml
cat > docs/providers/snapshots/perplexity.yaml << 'EOF'
provider: perplexity
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: false
  tier_type: null
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: true
  models: []
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null
paid_tier:
  available: true
  models:
    - name: sonar
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: null
      cost_per_1m_input: 1.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 1.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
    - name: sonar-reasoning
      context_window: 200000
      max_input_tokens: 200000
      max_output_tokens: null
      cost_per_1m_input: 1.00
      cost_per_1m_input_long: null
      cost_per_1m_output: 5.00
      cost_per_1m_output_long: null
      cost_per_1m_input_cached: null
      status: active
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: false
  structured_output: false
  thinking_mode: true
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]
data_privacy:
  trains_on_free_tier: null
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "Real-time web search grounded responses — unique for news flow and market data research. Not suitable for tool calling or JSON extraction. No key configured yet."
EOF

# Write docs/providers/snapshots/cloudflare.yaml
cat > docs/providers/snapshots/cloudflare.yaml << 'EOF'
provider: cloudflare
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: "@cf/meta/llama-3.3-70b-instruct"
      context_window: 8192
      max_input_tokens: 8192
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null
    rpd: null
    tpm: null            # 10,000 neurons/day; not token-denominated
    input_tpm: null
    concurrent_requests: null
    reset_window: calendar_day
paid_tier:
  available: true
  models: []             # $0.011 per 1000 neurons beyond free allowance
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: false
  structured_output: false
  thinking_mode: false
  streaming: true
  vision: true
  embeddings: true
  modalities: [text, image]
data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: true
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "10k neurons/day standing free. Best from inside Workers runtime. Context capped at 8k — not suitable for 100k+ research. No key configured yet."
EOF

# Write docs/providers/snapshots/sambanova.yaml
cat > docs/providers/snapshots/sambanova.yaml << 'EOF'
provider: sambanova
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: true
  tier_type: standing
  credit_amount_usd: null
  credit_expiry_days: null
  privacy_warning: null
  signup_required: true
  cc_required: false
  models:
    - name: Meta-Llama-3.3-70B-Instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: Meta-Llama-4-Scout-17B-16E-Instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
    - name: DeepSeek-R1
      context_window: 32768
      max_input_tokens: 32768
      max_output_tokens: 16384
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: 20
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: rolling_minute
paid_tier:
  available: false
  models: []
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: false
  structured_output: false
  thinking_mode: true
  streaming: true
  vision: false
  embeddings: false
  modalities: [text]
data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: false
  soc2: false
reliability:
  known_instability: false
  requires_backoff: false
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "Fast RDU inference on Llama + DeepSeek. Generous free tier with no tool calling. No key configured yet."
EOF

# Write docs/providers/snapshots/huggingface.yaml
cat > docs/providers/snapshots/huggingface.yaml << 'EOF'
provider: huggingface
last_checked: 2026-05-01
source: agent-research
free_tier:
  available: true
  tier_type: credits
  credit_amount_usd: 2.00       # PRO users get ~$2/mo credit allocation
  credit_expiry_days: 30
  privacy_warning: null
  signup_required: true
  cc_required: false            # PRO is $9/mo; free tier very limited
  models:
    - name: meta-llama/Llama-3.3-70B-Instruct
      context_window: 131072
      max_input_tokens: 131072
      max_output_tokens: 8192
      status: active
      verified: null
      last_verified: null
      last_verified_latency_ms: null
      verification_error: null
  rate_limits:
    rpm: null
    rpd: null
    tpm: null
    input_tpm: null
    concurrent_requests: null
    reset_window: null
paid_tier:
  available: true
  models: []                    # Routes to Together/Fireworks/SambaNova behind the scenes
  batching:
    available: false
    discount_pct: null
    max_batch_size: null
    turnaround_hours: null
    notes: null
  prompt_caching:
    available: false
    min_cacheable_tokens: null
    ttl_seconds: null
    cost_per_1m_cached_writes: null
    cost_per_1m_cached_reads: null
    notes: null
capabilities:
  tool_calling: false
  structured_output: false
  thinking_mode: false
  streaming: true
  vision: false
  embeddings: true
  modalities: [text]
data_privacy:
  trains_on_free_tier: false
  retention_days: null
  zero_retention_on_paid: false
  gdpr_compliant: true
  soc2: false
reliability:
  known_instability: false
  requires_backoff: true
  geographic_restrictions: []
verification:
  method: skipped
  probe_prompt: null
  probe_model_alias: null
  github_secret_key: null
notes: "Best for model discovery and evaluation. Routes to upstream providers — not a direct API for production. Free tier very limited; PRO $9/mo gives ~$2 credits. No key configured yet."
EOF
```

- [ ] **Step 6: Commit research-only snapshots**

```bash
git add docs/providers/snapshots/
git commit -m "feat(provider-review): seed initial snapshots for 11 research-only providers"
```

---

## Task 7: Add `# llm-decision:` tags to config/model_modes.yaml

Augment the existing `[tier: ...]` comments with `# llm-decision:` tags. Existing prose is preserved — the new tag line is inserted above it.

**Files:**
- Modify: `config/model_modes.yaml`

- [ ] **Step 1: Add tags to extraction-tier entries (phases 1, 2, 7C)**

Open `config/model_modes.yaml` and add `# llm-decision:` lines as shown. Make these exact edits:

```
FIND:
  # Phase 1 — alt-data extraction (4 parallel segments, ~500 tokens each)
  # [tier: extraction] — sentiment scores, CTA signals, options flow numbers

REPLACE WITH:
  # Phase 1 — alt-data extraction (4 parallel segments, ~500 tokens each)
  # llm-decision: extraction free-preferred throughput-constrained
  # [tier: extraction] — sentiment scores, CTA signals, options flow numbers
```

Repeat the same pattern for every phase tagged `[tier: extraction]`:
- Phase 2 (`inst-institutional-flows`, `inst-hedge-fund-intel`)
- Phase 7C analyst fan-out (`analyst-` prefix entries)

- [ ] **Step 2: Add tags to reasoning-tier entries (phase 7 master-digest, phase 7D pm-rebalance)**

```
FIND:
  # Phase 7 — master digest synthesis (~8k tokens in, reads all phase 1–6 outputs)
  # [tier: reasoning] — THE highest-stakes call; reconciles 20+ signals into

REPLACE WITH:
  # Phase 7 — master digest synthesis (~8k tokens in, reads all phase 1–6 outputs)
  # llm-decision: reasoning free-preferred
  # [tier: reasoning] — THE highest-stakes call; reconciles 20+ signals into
```

And for pm-rebalance:

```
FIND:
  # Phase 7D — PM rebalance decision (~12k tokens in, reads all analyst payloads)
  # [tier: reasoning] — Portfolio allocation decision with real investment stakes.

REPLACE WITH:
  # Phase 7D — PM rebalance decision (~12k tokens in, reads all analyst payloads)
  # llm-decision: reasoning free-preferred
  # [tier: reasoning] — Portfolio allocation decision with real investment stakes.
```

- [ ] **Step 3: Add tags to research-tier entry (phase 9)**

```
FIND:
  # Phase 9 — pipeline evolution / post-mortem (~4k tokens in)
  # [tier: research] — Evaluates prior-day prediction quality

REPLACE WITH:
  # Phase 9 — pipeline evolution / post-mortem (~4k tokens in)
  # llm-decision: research free-preferred
  # [tier: research] — Evaluates prior-day prediction quality
```

- [ ] **Step 4: Add tags to defaults section**

```
FIND:
# Default model per DIGI_LLM_MODE (applies to phases without a phase_models entry).

REPLACE WITH:
# Default model per DIGI_LLM_MODE (applies to phases without a phase_models entry).
# llm-decision: research free-preferred
# Gemini Flash: best free throughput for phases 3-5 (macro, asset class, equity research tier)
```

- [ ] **Step 5: Verify the scanner finds all tagged entries**

```bash
python -c "
from scripts.provider_review.bootstrap import extract_decision_comments
decisions = extract_decision_comments(['config/model_modes.yaml'])
print(f'Found {len(decisions)} llm-decision entries:')
for d in decisions:
    print(f'  line {d[\"line\"]}: {d[\"tags\"]} -> {d[\"model\"]}')
"
```

Expected: at least 8 entries (extraction ×6, reasoning ×2, research ×2, defaults ×1).

- [ ] **Step 6: Commit**

```bash
git add config/model_modes.yaml
git commit -m "feat(provider-review): add # llm-decision: tags to model_modes.yaml"
```

---

## Task 8: Write the GitHub Actions workflow

**Files:**
- Create: `.github/workflows/provider-review.yml`

- [ ] **Step 1: Write the workflow file**

```yaml
# .github/workflows/provider-review.yml
name: Provider review

# Weekly automated LLM provider review.
# Step 1: Probe all providers with live API calls.
# Step 2: Assemble context package (snapshots + pricing + decision comments).
# Step 3: Claude agent researches, updates snapshots, evaluates decisions, writes findings.
# Step 4: Open GitHub issues for each novel trigger condition found.
#
# Feature-flagged on CLAUDE_CODE_OAUTH_TOKEN. Silent-exit when absent.
# Budget: 1 Claude invocation/week.

on:
  schedule:
    - cron: '0 0 * * 0'   # Every Sunday 00:00 UTC
  workflow_dispatch:        # Manual trigger anytime

permissions:
  contents: write           # agent commits snapshot updates
  issues: write

jobs:
  review:
    name: Weekly provider review
    runs-on: ubuntu-latest
    timeout-minutes: 30

    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Configure git for agent commits
        run: |
          git config user.name "github-actions[bot]"
          git config user.email "github-actions[bot]@users.noreply.github.com"

      - name: Check Claude auth present
        id: keycheck
        env:
          KEY: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
        run: |
          if [ -n "${KEY:-}" ]; then
            echo "present=true" >> "$GITHUB_OUTPUT"
          else
            echo "::notice::CLAUDE_CODE_OAUTH_TOKEN not set — provider review disabled."
            echo "present=false" >> "$GITHUB_OUTPUT"
          fi

      - name: Set up Python
        if: steps.keycheck.outputs.present == 'true'
        uses: actions/setup-python@v5
        with:
          python-version: '3.12'

      - name: Install dependencies
        if: steps.keycheck.outputs.present == 'true'
        run: pip install openai httpx pyyaml

      # ── Step 1: Probe ───────────────────────────────────────────────────────
      - name: Step 1 — Probe providers
        if: steps.keycheck.outputs.present == 'true'
        env:
          GEMINI_API_KEY: ${{ secrets.GEMINI_API_KEY }}
          GROQ_API_KEY: ${{ secrets.GROQ_API_KEY }}
          CEREBRAS_API_KEY: ${{ secrets.CEREBRAS_API_KEY }}
          MISTRAL_API_KEY: ${{ secrets.MISTRAL_API_KEY }}
          NVIDIA_API_KEY: ${{ secrets.NVIDIA_API_KEY }}
          OLLAMA_API_KEY: ${{ secrets.OLLAMA_API_KEY }}
          OPENROUTER_API_KEY: ${{ secrets.OPENROUTER_API_KEY }}
          DEEPSEEK_API_KEY: ${{ secrets.DEEPSEEK_API_KEY }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          mkdir -p /tmp/review
          python scripts/provider_review/probe.py

      # ── Step 2: Bootstrap ───────────────────────────────────────────────────
      - name: Step 2 — Bootstrap context
        if: steps.keycheck.outputs.present == 'true'
        run: python scripts/provider_review/bootstrap.py

      # ── Step 3: Claude agent ────────────────────────────────────────────────
      - name: Step 3 — Claude agent research and evaluation
        if: steps.keycheck.outputs.present == 'true'
        env:
          CLAUDE_CODE_OAUTH_TOKEN: ${{ secrets.CLAUDE_CODE_OAUTH_TOKEN }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
        run: |
          TODAY=$(date -u +%Y-%m-%d)
          claude --print "
          You are performing the weekly LLM provider review for the DigiThings project.

          Your context package is in /tmp/review/:
          - snapshots.json: current provider snapshots (update these)
          - probe-results.json: live probe results from this run
          - litellm-pricing.json: upstream LiteLLM pricing data
          - decisions.json: all # llm-decision: tagged config entries (file + line + tags + model)
          - manifest.json: summary counts

          Execute these steps in order:

          STEP A — RESEARCH: For each provider in snapshots.json, use web search to verify
          the current free-tier quota limits, model availability, and pricing. Cross-reference
          against probe-results.json and litellm-pricing.json.

          STEP B — UPDATE SNAPSHOTS: Write updated YAML to docs/providers/snapshots/*.yaml.
          For each model in each snapshot:
          - Set verified=true/false from probe-results.json (match on provider name)
          - Set last_verified=$TODAY and last_verified_latency_ms from probe results
          - Set verification_error from probe results error field (null if ok/skipped)
          - Update status to paid-only if probe returned auth error (401/403)
          - Update quota numbers from your research findings

          STEP C — REGENERATE CATALOG: Rewrite docs/LLM_PROVIDERS.md so the free-tier
          quota numbers for each provider match the updated snapshots. Preserve the
          existing document structure and prose style exactly.

          STEP D — EVALUATE DECISIONS: For each entry in decisions.json, assess:
          1. Is the current model still verified-active in the updated snapshot?
          2. Has a materially better free option emerged for this decision role
             (extraction/research/reasoning)?
          3. Is the cost delta for a paid upgrade now justified vs current free option?
          Produce a one-line cost-benefit score per entry.

          STEP E — WRITE FINDINGS: Write /tmp/review/findings.json as a JSON array.
          Each object must have these exact keys:
          {
            \"provider\": \"<provider_name>\",
            \"trigger\": \"<quota_drop|model_deprecated|better_free|cost_increase>\",
            \"summary\": \"<one-line description under 80 chars>\",
            \"detail\": \"<full explanation>\",
            \"config_file\": \"<file:line or N/A>\",
            \"tags\": [\"<tag1>\", \"<tag2>\"],
            \"current_model\": \"<model_id or N/A>\",
            \"cost_benefit_table\": \"| Option | Score | Cost/run | Notes |\\n|---|---|---|---|\\n...\",
            \"recommendation\": \"<one-line recommendation>\"
          }
          Write [] if no trigger conditions are found this week.

          STEP F — COMMIT: Stage and commit all changes to docs/providers/snapshots/ and
          docs/LLM_PROVIDERS.md with message:
          'docs(providers): weekly snapshot update $TODAY [skip ci]'

          Do NOT create GitHub issues — Step 4 handles that.
          Do NOT modify any files outside docs/providers/ and docs/LLM_PROVIDERS.md.
          "

      # ── Step 4: Issue creation ──────────────────────────────────────────────
      - name: Step 4 — Create issues for findings
        if: steps.keycheck.outputs.present == 'true'
        env:
          GH_TOKEN: ${{ secrets.DIGITHINGS_PROJECT_TOKEN }}
          REPO: ${{ github.repository }}
        run: python scripts/provider_review/create_issues.py
```

- [ ] **Step 2: Commit the workflow**

```bash
git add .github/workflows/provider-review.yml
git commit -m "feat(provider-review): add weekly provider-review workflow"
```

---

## Task 9: Smoke test

Verify the scripts work end-to-end with a dry run before the first scheduled execution.

- [ ] **Step 1: Run all unit tests**

```bash
pytest tests/provider_review/ -m unit -v
```

Expected: 14 tests pass.

- [ ] **Step 2: Run bootstrap with real snapshot files**

```bash
python scripts/provider_review/bootstrap.py
```

Expected output:
```
Bootstrap: assembling context package...
  snapshots: 20 providers loaded
  litellm-pricing: <N> models
  decisions: <N> # llm-decision: entries found
  probe-results: not found at /tmp/review/probe-results.json — skipping
  manifest: {'snapshot_count': 20, ...}
Done — /tmp/review/ ready for agent.
```

- [ ] **Step 3: Run probe (dry run — will skip providers without local env keys)**

```bash
python scripts/provider_review/probe.py
```

Expected: each configured provider shows `SKIPPED` (no keys in local env unless you've sourced .env). No errors.

- [ ] **Step 4: Verify create_issues does nothing with empty findings**

```bash
echo "[]" > /tmp/review/findings.json
REPO=digithings-ai/digithings GH_TOKEN=$(gh auth token) python scripts/provider_review/create_issues.py
```

Expected: `findings.json is empty — no issues to create.`

- [ ] **Step 5: Trigger workflow manually to confirm CI wiring**

```bash
gh workflow run provider-review.yml --repo digithings-ai/digithings
gh run list --workflow=provider-review.yml --limit=1
```

Expected: workflow appears in the run list and starts executing. Monitor for the 30-minute timeout.

- [ ] **Step 6: Final commit if any adjustments were made during smoke test**

```bash
git add -A
git commit -m "feat(provider-review): smoke test fixes" || echo "Nothing to commit"
```

---

## Post-implementation checklist

- [ ] All 14 unit tests pass: `pytest tests/provider_review/ -m unit -v`
- [ ] 20 snapshot files exist in `docs/providers/snapshots/`
- [ ] `# llm-decision:` tags present in `config/model_modes.yaml` (verified by bootstrap scanner)
- [ ] `provider-review.yml` workflow visible in GitHub Actions tab
- [ ] First manual workflow run completes without error
- [ ] At least one snapshot YAML has `verified: true` after the first agent run
