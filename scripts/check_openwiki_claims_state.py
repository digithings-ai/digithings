#!/usr/bin/env python3
"""Check that OpenWiki claim sidecars and the page manifest agree (DIG-4382).

OpenWiki loads every ``openwiki/.claims/**/*.json`` sidecar during preflight and
refuses to start when one has no ``pageVersion`` — a shape the two digivoice
sidecars from commit 4b0f8ef05 had, because their pages were added without their
``openwiki/.page-manifest.json`` entries. The scheduled ``OpenWiki Update`` then
exits 1 before it writes a page or opens a PR. Separately, a sidecar with claims
but no ``verification`` block makes the run's finish step fail, so that state
must not merge either.

What it asserts
---------------
Errors (exit 1):
* every sidecar parses as a JSON object and carries a ``pageVersion`` of the
  form ``sha256:<64 lowercase hex>``;
* every sidecar names a page that exists;
* every sidecar with a non-empty ``claims`` list carries a ``verification``
  object with non-empty ``by`` and ``at``;
* every manifest entry has a well-formed ``pageVersion``;
* an unverified sidecar must also have a manifest entry with the same
  ``pageVersion`` (the exact half-written state this check exists for).

Warnings (reported, exit 0), because an interrupted run legitimately leaves
them and the workflow turns that run into a mergeable partial PR:
* a verified sidecar with no manifest entry, or one whose manifest entry has a
  different ``pageVersion`` (OpenWiki rebuilds the manifest at finish);
* a manifest entry with no sidecar.

Usage
-----
::

    python3 scripts/check_openwiki_claims_state.py
    python3 scripts/check_openwiki_claims_state.py --format json

Exit code is ``0`` when there are no errors, ``1`` when there is at least one.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

PAGE_VERSION_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
MANIFEST_SCHEMA_VERSION = 1


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def _sidecar_pages(root: Path) -> dict[str, Path]:
    """Return page path -> sidecar file for every JSON sidecar."""
    claims_dir = root / "openwiki" / ".claims"
    pages: dict[str, Path] = {}
    if not claims_dir.is_dir():
        return pages
    for sidecar in sorted(claims_dir.rglob("*.json")):
        relative = sidecar.relative_to(claims_dir).with_suffix(".md")
        pages[f"/openwiki/{relative.as_posix()}"] = sidecar
    return pages


def _load_manifest(root: Path) -> tuple[dict[str, dict[str, object]], list[Finding]]:
    """Return manifest page entries plus any load error."""
    manifest_path = root / "openwiki" / ".page-manifest.json"
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [
            Finding("error", "manifest_missing", "openwiki/.page-manifest.json", "manifest file is missing")
        ]
    except json.JSONDecodeError as error:
        return {}, [
            Finding(
                "error",
                "manifest_invalid_json",
                "openwiki/.page-manifest.json",
                f"manifest is not valid JSON: {error}",
            )
        ]
    if not isinstance(manifest, dict) or manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
        return {}, [
            Finding(
                "error",
                "manifest_schema",
                "openwiki/.page-manifest.json",
                f"manifest must be an object with schemaVersion {MANIFEST_SCHEMA_VERSION}",
            )
        ]
    pages = manifest.get("pages")
    if not isinstance(pages, dict):
        return {}, [
            Finding(
                "error",
                "manifest_schema",
                "openwiki/.page-manifest.json",
                "manifest must carry a pages object",
            )
        ]
    return pages, []


def _verification_error(display: str, payload: dict[str, object]) -> Finding | None:
    """Return the missing/invalid verification finding for a claim-bearing sidecar, if any."""
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return None
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        return Finding(
            "error", "sidecar_missing_verification", display, "sidecar has claims but no verification"
        )
    by = verification.get("by")
    at = verification.get("at")
    if not (isinstance(by, str) and by.strip()) or not (isinstance(at, str) and at.strip()):
        return Finding(
            "error",
            "sidecar_bad_verification",
            display,
            "verification must carry non-empty by and at",
        )
    return None


def _sidecar_findings(page: str, sidecar: Path, root: Path, manifest: dict[str, dict[str, object]]) -> list[Finding]:
    findings: list[Finding] = []
    display = str(sidecar.relative_to(root))
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [Finding("error", "sidecar_invalid_json", display, f"not valid JSON: {error}")]
    if not isinstance(payload, dict):
        return [Finding("error", "sidecar_schema", display, "sidecar must be a JSON object")]

    page_version = payload.get("pageVersion")
    if page_version is None:
        findings.append(
            Finding("error", "sidecar_missing_page_version", display, "sidecar has no pageVersion")
        )
    elif not isinstance(page_version, str) or not PAGE_VERSION_RE.match(page_version):
        findings.append(
            Finding(
                "error",
                "sidecar_bad_page_version",
                display,
                "pageVersion must match sha256:<64 lowercase hex>",
            )
        )
        page_version = None

    if not (root / page.lstrip("/")).is_file():
        findings.append(
            Finding("error", "sidecar_page_missing", display, f"page {page} does not exist")
        )

    verification_finding = _verification_error(display, payload)
    if verification_finding is not None:
        findings.append(verification_finding)

    entry = manifest.get(page)
    entry_version = entry.get("pageVersion") if isinstance(entry, dict) else None
    pairing_ok = isinstance(page_version, str) and entry_version == page_version
    if not pairing_ok:
        # An unverified sidecar with no matching manifest entry is the half-written
        # shape that breaks the run; a verified one is an interrupted-run artifact
        # OpenWiki rebuilds at finish, so it only warns.
        severity = "error" if verification_finding is not None else "warning"
        code = "sidecar_missing_manifest_entry" if entry is None else "page_version_mismatch"
        message = (
            f"no .page-manifest.json entry for {page}"
            if entry is None
            else f"sidecar pageVersion {page_version} != manifest {entry_version}"
        )
        findings.append(Finding(severity, code, display, message))
    return findings


def check(root: Path = REPO_ROOT) -> list[Finding]:
    """Return every sidecar/manifest inconsistency below ``root``."""
    manifest, findings = _load_manifest(root)
    sidecars = _sidecar_pages(root)

    if findings:
        # A manifest that did not load makes every pairing check meaningless;
        # report the single real problem instead of one line per sidecar.
        return findings

    for page, entry in sorted(manifest.items()):
        entry_version = entry.get("pageVersion") if isinstance(entry, dict) else None
        if not isinstance(entry_version, str) or not PAGE_VERSION_RE.match(entry_version):
            findings.append(
                Finding(
                    "error",
                    "manifest_bad_page_version",
                    "openwiki/.page-manifest.json",
                    f"entry {page} has no valid pageVersion",
                )
            )
        if page not in sidecars:
            findings.append(
                Finding(
                    "warning",
                    "manifest_missing_sidecar",
                    "openwiki/.page-manifest.json",
                    f"page entry {page} has no claim sidecar",
                )
            )

    for page, sidecar in sidecars.items():
        findings.extend(_sidecar_findings(page, sidecar, root, manifest))
    return findings


def main(argv: list[str] | None = None) -> int:
    """Run the check and print findings; return the process exit code."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=REPO_ROOT, help="repository root")
    parser.add_argument("--format", choices=("text", "json"), default="text")
    args = parser.parse_args(argv)

    findings = check(args.root.resolve())
    errors = [finding for finding in findings if finding.severity == "error"]
    if args.format == "json":
        print(json.dumps([asdict(finding) for finding in findings], indent=2))
    else:
        for finding in findings:
            print(f"{finding.severity}: {finding.path}: {finding.message} [{finding.code}]")
        if errors:
            print(f"\n{len(errors)} OpenWiki sidecar/manifest error(s) found.")
        elif findings:
            print(f"OpenWiki sidecars ok; {len(findings)} warning(s).")
        else:
            print("OpenWiki claim sidecars and page manifest agree.")
    return 1 if errors else 0


if __name__ == "__main__":
    sys.exit(main())
