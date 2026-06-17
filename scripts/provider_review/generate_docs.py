"""
Generate/update docs/free-providers/*.md from docs/providers/snapshots/*.yaml.

Called by the provider-review workflow after snapshots are updated to keep
the human-readable docs in sync with the machine-readable data.

Usage:
    python scripts/provider_review/generate_docs.py [--dry-run]

For each snapshot YAML:
  - If a matching docs/free-providers/<slug>.md exists: update rate limits,
    model table, and verified_at in the frontmatter.
  - If no matching .md exists: emit a warning (manual doc creation needed for
    providers that have complex DigiThings-specific context).

Also regenerates docs/free-providers/_index.md from all snapshots.

Exit codes:
    0  — all files up to date (or --dry-run)
    1  — one or more files updated (non-zero so CI can detect changes)
"""

from __future__ import annotations

import argparse
import re
import sys
from datetime import date
from pathlib import Path
from typing import Any

import yaml  # pip install pyyaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SNAPSHOTS_DIR = REPO_ROOT / "docs" / "providers" / "snapshots"
DOCS_DIR = REPO_ROOT / "docs" / "free-providers"

PRIVACY_LABELS = {
    "trains_on_data": "⚠️ trains on free-tier data",
    "no_training": "✅ no training",
    "regional_law": "⚠️ regional law (see notes)",
    "unknown": "? not published",
}


def load_snapshot(path: Path) -> dict[str, Any]:
    with path.open() as f:
        return yaml.safe_load(f)


def update_frontmatter(doc_path: Path, snap: dict[str, Any], today: str) -> bool:
    """Update verified_at in the .md frontmatter. Returns True if changed."""
    text = doc_path.read_text()

    # Extract frontmatter block
    m = re.match(r"^---\n(.*?)\n---\n", text, re.DOTALL)
    if not m:
        print(f"  [WARN] No frontmatter found in {doc_path.name} — skipping update")
        return False

    fm_block = m.group(1)
    fm = yaml.safe_load(fm_block)

    changed = False

    # Update verified_at
    if fm.get("verified_at") != today:
        fm_block = re.sub(
            r"^verified_at:.*$",
            f"verified_at: {today}",
            fm_block,
            flags=re.MULTILINE,
        )
        changed = True

    if not changed:
        return False

    new_text = f"---\n{fm_block}\n---\n" + text[m.end():]
    doc_path.write_text(new_text)
    return True


def update_model_table(doc_path: Path, snap: dict[str, Any]) -> bool:
    """Replace the ## Free-Tier Models table with data from snapshot. Returns True if changed."""
    models = snap.get("free_tier", {}).get("models", [])
    if not models:
        return False

    # Build table
    rows = ["| Model ID | Context Window | Max Output | Notes |",
            "|---|---|---|---|"]
    for m in models:
        name = f"`{m['name']}`"
        ctx = f"{m['context_window']:,}" if m.get("context_window") else "—"
        out = f"{m['max_output_tokens']:,}" if m.get("max_output_tokens") else "—"
        status = m.get("status", "active")
        notes = "active" if status == "active" else f"**{status}**"
        if m.get("verification_error"):
            notes = f"⚠️ {m['verification_error']}"
        rows.append(f"| {name} | {ctx} | {out} | {notes} |")

    new_table = "\n".join(rows)

    text = doc_path.read_text()
    # Replace table block between ## Free-Tier Models header and the next ---
    pattern = r"(## Free-Tier Models.*?\n)\|[^\n]*\n(?:\|[^\n]*\n)+"
    replacement = r"\g<1>" + new_table + "\n"
    new_text, n = re.subn(pattern, replacement, text, flags=re.DOTALL)

    if n == 0 or new_text == text:
        return False

    doc_path.write_text(new_text)
    return True


def update_changelog(doc_path: Path, today: str, message: str) -> None:
    """Append a row to the Changelog table."""
    text = doc_path.read_text()
    # Find last changelog row and insert after it
    changelog_row = f"| {today} | {message} | provider-review scan |"
    if changelog_row in text:
        return  # already present

    # Insert before the last blank line / end of file
    pattern = r"(\| \d{4}-\d{2}-\d{2} \|[^\n]*\n)(?!.*\| \d{4}-\d{2}-\d{2} \|)"
    replacement = r"\g<1>" + changelog_row + "\n"
    new_text = re.sub(pattern, replacement, text, flags=re.DOTALL)
    if new_text != text:
        doc_path.write_text(new_text)


def build_index(snapshots: list[dict[str, Any]], today: str) -> str:
    """Regenerate _index.md content from all snapshots."""
    standing = []
    trial = []
    credit = []

    for snap in sorted(snapshots, key=lambda s: s.get("provider", "")):
        ft = snap.get("free_tier", {})
        if not ft.get("available"):
            continue

        slug = snap.get("provider", "unknown").lower().replace(" ", "-").replace("_", "-")
        name = snap.get("provider", slug)
        tier_type = ft.get("tier_type", "unknown")
        rl = ft.get("rate_limits", {})
        models = ft.get("models", [])
        top_model = models[0]["name"] if models else "—"
        max_ctx = max((m.get("context_window", 0) for m in models), default=0)
        ctx_str = f"{max_ctx // 1024}k" if max_ctx >= 1024 else str(max_ctx)
        rpm = rl.get("rpm", "?")
        rpd = rl.get("rpd", "?")
        privacy_key = snap.get("data_privacy", {})
        trains = privacy_key.get("trains_on_free_tier")
        privacy = "⚠️ trains" if trains else ("✅" if trains is False else "?")

        row = f"| [{name}]({slug}.md) | `{top_model}` | {ctx_str} | {rpm} | {rpd} | {privacy} |"

        if tier_type == "standing":
            standing.append(row)
        elif tier_type in ("trial", "experiment"):
            trial.append(row)
        else:
            credit.append(row)

    header = f"""<!-- auto-generated by scripts/provider_review/generate_docs.py — do not edit by hand -->
<!-- last_generated: {today} -->

# Free-Provider Reference Index

Deep-reference documentation for every free-tier LLM API available for DigiThings.
Each file is derived from `docs/providers/snapshots/` and updated weekly by the `provider-review` workflow.

**Setup guides**: [`docs/providers/`](../providers/)
**Master catalog**: [`docs/LLM_PROVIDERS.md`](../LLM_PROVIDERS.md)
**Machine-readable snapshots**: [`docs/providers/snapshots/`](../providers/snapshots/)

---

## Standing Free (no expiry, no credit card)

| Provider | Top Model | Max Context | RPM | RPD | Privacy |
|---|---|---|---|---|---|
"""
    trial_header = """
## Trial / Experiment (evaluation only)

| Provider | Top Model | Max Context | RPM | RPD | Privacy |
|---|---|---|---|---|---|
"""
    credit_header = """
## Credit-Based (one-time grant or small starter)

| Provider | Top Model | Max Context | RPM | RPD | Privacy |
|---|---|---|---|---|---|
"""
    footer = f"\n---\n\n*Generated: {today} · Next scan: weekly via `provider-review` workflow*\n"

    parts = [header]
    parts += [r + "\n" for r in standing]
    parts.append(trial_header)
    parts += [r + "\n" for r in trial]
    parts.append(credit_header)
    parts += [r + "\n" for r in credit]
    parts.append(footer)
    return "".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(description="Regenerate docs/free-providers/ from YAML snapshots")
    parser.add_argument("--dry-run", action="store_true", help="Print changes without writing files")
    args = parser.parse_args()

    today = date.today().isoformat()
    updated: list[str] = []
    snapshots: list[dict[str, Any]] = []

    for snap_path in sorted(SNAPSHOTS_DIR.glob("*.yaml")):
        snap = load_snapshot(snap_path)
        snapshots.append(snap)

        slug = snap.get("provider", snap_path.stem).lower().replace(" ", "-").replace("_", "-")
        doc_path = DOCS_DIR / f"{slug}.md"

        if not doc_path.exists():
            print(f"  [SKIP] No doc found for {snap_path.name} (slug: {slug}) — manual creation needed")
            continue

        file_changed = False

        if not args.dry_run:
            if update_frontmatter(doc_path, snap, today):
                file_changed = True
            if update_model_table(doc_path, snap):
                file_changed = True
            if file_changed:
                update_changelog(doc_path, today, "Automated snapshot sync")
                updated.append(doc_path.name)
                print(f"  [UPDATED] {doc_path.name}")
            else:
                print(f"  [OK] {doc_path.name} — no changes")
        else:
            print(f"  [DRY-RUN] Would check {doc_path.name}")

    # Regenerate index
    index_content = build_index(snapshots, today)
    index_path = DOCS_DIR / "_index.md"
    if not args.dry_run:
        if not index_path.exists() or index_path.read_text() != index_content:
            index_path.write_text(index_content)
            updated.append("_index.md")
            print("  [UPDATED] _index.md")

    if updated:
        print(f"\nUpdated {len(updated)} file(s): {', '.join(updated)}")
        return 1  # non-zero so CI detects changes
    else:
        print("\nAll provider docs are up to date.")
        return 0


if __name__ == "__main__":
    sys.exit(main())
