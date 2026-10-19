#!/usr/bin/env python3
"""Check that OpenWiki claim sidecars and the page manifest agree (DIG-4382).

OpenWiki loads every ``openwiki/.claims/**/*.json`` sidecar during preflight and
validates each one against a strict zod schema, and refuses the run when one is
rejected — a shape the two digivoice sidecars from commit 4b0f8ef05 hit, because
their pages were added without ``pageVersion`` or their
``openwiki/.page-manifest.json`` entries. Separately, a claim-bearing sidecar
without a durable ``verification`` block fails the run again at page coverage,
so neither state may merge.

What it asserts
---------------
The error rules mirror what OpenWiki 0.5.0 validates at preflight
(``store.js`` ``PageClaimsSchema``/``VerificationSchema``, strict objects) and at
manifest load (``page-manifest.js`` ``ManifestSchema``):

Errors (exit 1):
* every sidecar parses as a JSON object with exactly the ``schemaVersion``,
  ``pageVersion``, ``claims`` and (optional) ``verification`` keys;
* ``schemaVersion`` is the literal ``1`` (a JSON ``true`` is not);
* ``pageVersion`` matches ``sha256:<64 lowercase hex>``;
* ``claims`` is a list (possibly empty) of claim objects carrying non-empty
  ``id`` and ``statement`` strings and a non-empty ``evidence`` list of objects
  with non-empty ``resource``/``version`` strings;
* a non-empty ``claims`` list carries a ``verification`` object with non-empty
  ``by``/``at`` strings and no extra keys;
* every sidecar maps to a page that exists on disk;
* the manifest is an object with exactly ``schemaVersion`` and ``pages``,
  entries match ``sha256:<64 lowercase hex>`` (plus only the known optional
  provenance keys with well-formed values), and page keys are canonical
  ``/openwiki/**`` Markdown paths that are not reserved;
OpenWiki loads every ``openwiki/.claims/**/*.json`` sidecar during preflight and
validates each one against a strict zod schema, and refuses the run when one is
rejected — a shape the two digivoice sidecars from commit 4b0f8ef05 hit, because
their pages were added without ``pageVersion`` or their
``openwiki/.page-manifest.json`` entries. Separately, a claim-bearing sidecar
without a durable ``verification`` block fails the run again at page coverage,
so neither state may merge.

What it asserts
---------------
The error rules mirror what OpenWiki 0.5.0 validates at preflight
(``store.js`` ``PageClaimsSchema``/``VerificationSchema``, strict objects) and at
manifest load (``page-manifest.js`` ``ManifestSchema``):

Errors (exit 1):
* every sidecar parses as a JSON object with exactly the ``schemaVersion``,
  ``pageVersion``, ``claims`` and (optional) ``verification`` keys;
* ``schemaVersion`` is the literal ``1`` (a JSON ``true`` is not);
* ``pageVersion`` matches ``sha256:<64 lowercase hex>``;
* ``claims`` is a list (possibly empty) of claim objects carrying non-empty
  ``id`` and ``statement`` strings and a non-empty ``evidence`` list of objects
  with non-empty ``resource``/``version`` strings;
* a non-empty ``claims`` list carries a ``verification`` object with non-empty
  ``by``/``at`` strings and no extra keys;
* every sidecar maps to a page that exists on disk;
* the manifest is an object with exactly ``schemaVersion`` and ``pages``,
  entries match ``sha256:<64 lowercase hex>`` (plus only the known optional
  provenance keys with well-formed values), and page keys are canonical
  ``/openwiki/**`` Markdown paths that are not reserved;
* a claim-bearing sidecar must also have a manifest entry with the same
  ``pageVersion`` — the exact half-written state this check exists for.

Warnings (reported, exit 0), because an interrupted run legitimately leaves
them and the workflow turns that run into a mergeable partial PR:
* a verified sidecar with no manifest entry, or one whose manifest entry has a
  different ``pageVersion`` (OpenWiki rebuilds the manifest at finish);
* a manifest entry with no claim sidecar.

The check is deliberately structural and does not re-hash the Markdown bytes:
page bytes may lag the committed versions until the run's planner regenerates
them, and OpenWiki's durability proof covers the pages the run processes, where
it rewrites their sidecars itself.

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
import posixpath
import re
import sys
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent

PAGE_VERSION_RE = re.compile(r"^sha256:[a-f0-9]{64}$")
MANIFEST_SCHEMA_VERSION = 1
# Strict key sets mirrored from openwiki 0.5.0 (PageClaimsSchema, VerificationSchema
# and ManifestEntrySchema are all zod ``.strict()`` objects: extra keys are rejected).
SIDECAR_KEYS = frozenset({"schemaVersion", "pageVersion", "claims", "verification"})
VERIFICATION_KEYS = frozenset({"by", "at"})
CLAIM_KEYS = frozenset({"id", "statement", "evidence"})
EVIDENCE_KEYS = frozenset({"resource", "version"})
MANIFEST_KEYS = frozenset({"schemaVersion", "pages"})
MANIFEST_ENTRY_KEYS = frozenset({"gitHead", "sourceFingerprint", "pageVersion", "completedBy", "completedRunId"})
# Reserved OpenWiki wiki files (``paths.js`` ``RESERVED_WIKI_FILES``).
RESERVED_WIKI_FILES = frozenset({"index.md", "log.md", "instructions.md"})


@dataclass(frozen=True)
class Finding:
    severity: str
    code: str
    path: str
    message: str


def _nonempty_str(value: Any) -> bool:
    """Whether ``value`` is a string with non-whitespace content."""
    return isinstance(value, str) and value.strip() != ""


def _canonical_page_path(value: Any) -> str | None:
    """Mirror of openwiki 0.5.0 ``normalizeWikiPagePath`` for manifest page keys.

    Returns the canonical ``/openwiki/**.md`` path, or ``None`` when the value is
    not canonical (wrong root/format, traversal segments, ``.claims`` segment or
    a reserved basename), which the tool rejects at manifest load.
    """
    if not isinstance(value, str):
        return None
    slashed = value.replace("\\", "/")
    if any(segment in (".", "..") for segment in slashed.split("/")):
        return None
    unrooted = slashed.lstrip("/")
    rooted = unrooted if unrooted == "openwiki" or unrooted.startswith("openwiki/") else f"openwiki/{unrooted}"
    normalized = posixpath.normpath(f"/{rooted}")
    segments = normalized.lower().split("/")
    if (
        not normalized.startswith("/openwiki/")
        or not normalized.endswith(".md")
        or ".claims" in segments
        or normalized.rsplit("/", 1)[-1].lower() in RESERVED_WIKI_FILES
    ):
        return None
    if normalized != value:
        return None
    return normalized


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
    """Return manifest page entries plus load errors (empty pages on a fatal error)."""
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
    if not isinstance(manifest, dict) or not isinstance(manifest.get("schemaVersion"), int) or isinstance(
        manifest.get("schemaVersion"), bool
    ) or manifest.get("schemaVersion") != MANIFEST_SCHEMA_VERSION:
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
    extras = sorted(set(manifest) - MANIFEST_KEYS)
    finding = (
        Finding(
            "error",
            "manifest_schema",
            "openwiki/.page-manifest.json",
            f"manifest has unknown key(s): {', '.join(extras)}",
        )
        if extras
        else None
    )
    return pages, [finding] if finding else []


def _manifest_entry_error(page: str, entry: Any) -> Finding | None:
    """Mirror openwiki 0.5.0 ``ManifestEntrySchema`` (strict) for one manifest entry."""
    if not isinstance(entry, dict):
        return Finding(
            "error",
            "manifest_bad_entry",
            "openwiki/.page-manifest.json",
            f"entry {page} must be an object",
        )
    extras = sorted(set(entry) - MANIFEST_ENTRY_KEYS)
    if extras:
        return Finding(
            "error",
            "manifest_bad_entry",
            "openwiki/.page-manifest.json",
            f"entry {page} has unknown key(s): {', '.join(extras)}",
        )
    if not isinstance(entry.get("pageVersion"), str) or not PAGE_VERSION_RE.match(entry.get("pageVersion", "")):
        return Finding(
            "error",
            "manifest_bad_page_version",
            "openwiki/.page-manifest.json",
            f"entry {page} has no valid pageVersion",
        )
    if "gitHead" in entry and not _nonempty_str(entry["gitHead"]):
        return Finding("error", "manifest_bad_entry", "openwiki/.page-manifest.json", f"entry {page} has an empty gitHead")
    if "sourceFingerprint" in entry and not (
        isinstance(entry["sourceFingerprint"], str) and PAGE_VERSION_RE.match(entry["sourceFingerprint"])
    ):
        return Finding(
            "error",
            "manifest_bad_entry",
            "openwiki/.page-manifest.json",
            f"entry {page} has no valid sourceFingerprint",
        )
    if "completedBy" in entry and not _nonempty_str(entry["completedBy"]):
        return Finding(
            "error", "manifest_bad_entry", "openwiki/.page-manifest.json", f"entry {page} has an empty completedBy"
        )
    if "completedRunId" in entry:
        try:
            uuid.UUID(entry["completedRunId"])
        except (ValueError, AttributeError, TypeError):
            return Finding(
                "error", "manifest_bad_entry", "openwiki/.page-manifest.json", f"entry {page} has no valid completedRunId"
            )
    return None


def _verification_error(display: str, payload: dict[str, Any]) -> Finding | None:
    """Return the missing/invalid verification finding for a claim-bearing sidecar, if any."""
    claims = payload.get("claims")
    if not isinstance(claims, list) or not claims:
        return None
    verification = payload.get("verification")
    if not isinstance(verification, dict):
        return Finding(
            "error", "sidecar_missing_verification", display, "sidecar has claims but no verification"
        )
    if set(verification) - VERIFICATION_KEYS or not _nonempty_str(verification.get("by")) or not _nonempty_str(
        verification.get("at")
    ):
        return Finding(
            "error",
            "sidecar_bad_verification",
            display,
            "verification must hold exactly non-empty by and at",
        )
    return None


def _sidecar_shape_errors(display: str, payload: dict[str, Any]) -> list[Finding]:
    """Mirror openwiki 0.5.0 ``PageClaimsSchema`` (strict) rejects for one sidecar."""
    errors: list[Finding] = []
    extras = sorted(set(payload) - SIDECAR_KEYS)
    if extras:
        errors.append(
            Finding(
                "error",
                "sidecar_schema",
                display,
                f"sidecar has unknown key(s): {', '.join(extras)}",
            )
        )
    schema_version = payload.get("schemaVersion")
    if isinstance(schema_version, bool) or schema_version != 1:
        errors.append(
            Finding("error", "sidecar_schema", display, "schemaVersion must be the literal 1")
        )
    claims = payload.get("claims")
    if not isinstance(claims, list):
        errors.append(
            Finding("error", "sidecar_missing_claims", display, "sidecar has no claims array")
        )
        return errors
    for claim in claims:
        if (
            not isinstance(claim, dict)
            or set(claim) - CLAIM_KEYS
            or not _nonempty_str(claim.get("id"))
            or not _nonempty_str(claim.get("statement"))
        ):
            errors.append(
                Finding(
                    "error",
                    "sidecar_bad_claim",
                    display,
                    "each claim must hold non-empty id and statement",
                )
            )
            continue
        evidence = claim.get("evidence")
        valid_evidence = isinstance(evidence, list) and len(evidence) > 0 and all(
            isinstance(item, dict)
            and not (set(item) - EVIDENCE_KEYS)
            and _nonempty_str(item.get("resource"))
            and _nonempty_str(item.get("version"))
            for item in evidence
        )
        if not valid_evidence:
            errors.append(
                Finding(
                    "error",
                    "sidecar_bad_claim",
                    display,
                    f"claim {claim.get('id')} needs non-empty evidence with resource and version",
                )
            )
    return errors


def _sidecar_findings(page: str, sidecar: Path, root: Path, manifest: dict[str, dict[str, object]]) -> list[Finding]:
    findings: list[Finding] = []
    display = str(sidecar.relative_to(root))
    try:
        payload = json.loads(sidecar.read_text(encoding="utf-8"))
    except json.JSONDecodeError as error:
        return [Finding("error", "sidecar_invalid_json", display, f"not valid JSON: {error}")]
    if not isinstance(payload, dict):
        return [Finding("error", "sidecar_schema", display, "sidecar must be a JSON object")]

    findings = _sidecar_shape_errors(display, payload)

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
        if _canonical_page_path(page) is None:
            findings.append(
                Finding(
                    "error",
                    "manifest_bad_page_path",
                    "openwiki/.page-manifest.json",
                    f"page key {page} is not a canonical OpenWiki Markdown path",
                )
            )
        entry_error = _manifest_entry_error(page, entry)
        if entry_error is not None:
            findings.append(entry_error)
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
