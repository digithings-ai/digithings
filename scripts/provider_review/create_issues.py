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
    """Render the GitHub issue body for a provider finding."""
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
    """Read findings.json and open one GitHub issue per novel finding."""
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
