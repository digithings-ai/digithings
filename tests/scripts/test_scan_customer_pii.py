"""Pin that committed customer PII cannot reach the repo.

DIG-1498 R5, third path. `scripts/index_occ_tickets.py` writes full
non-anonymized Zammad ticket bodies into the digisearch `occ_tickets` index --
customer names, customer emails and `[internal]` staff notes -- and DIG-1210
was the first uncovered path for the same data. A formatter change does not
catch the next one and a `.gitignore` line does not either: gitignore governs
untracked files only, so `git add -f`, a renamed export, or an artifact
committed from a machine with no root `.gitignore` all walk straight past it.

These assertions run the real scanner over real git repositories. The load-
bearing one is `test_this_repository_is_clean`: a scanner that fires on
fixtures while firing on the repo it ships in is a red CI job nobody reads,
which is worse than no scanner. That assertion is what forces the
false-positive surface to be measured and allowlisted rather than assumed.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]

# The scanner lives in scripts/ and imports digitrace by sys.path insert, so it
# is loaded the way CI loads it -- as a script, not as an installed package.
sys.path.insert(0, str(REPO_ROOT / "scripts"))

pytestmark = pytest.mark.unit

# A ticket body as `scripts/index_occ_tickets.py` writes it: the customer who
# wrote in, and the staff-only note staff wrote back. Both unmasked.
TICKET_LINE = (
    "Ticket 4711 from jane.doe@kunde-beispiel.de: "
    "[internal] escalate to the account owner, card on file."
)
REGISTRATION_LINE = "Handelsregister: HRB 12345 Amtsgericht Muenchen, USt-IdNr. DE123456789"


@pytest.fixture(scope="module")
def scanner():
    import scan_customer_pii

    return scan_customer_pii


@pytest.fixture()
def fixture_repo(tmp_path: Path) -> Path:
    """A throwaway git repo whose tracked files the scanner will walk."""
    repo = tmp_path / "repo"
    repo.mkdir()
    env = {
        "GIT_CONFIG_GLOBAL": str(tmp_path / "gitconfig-absent"),
        "GIT_CONFIG_SYSTEM": str(tmp_path / "gitconfig-absent"),
        "HOME": str(tmp_path),
        "PATH": "/usr/bin:/bin",
    }
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=repo, check=True, env=env)
    # The real root rules travel with the fixture on purpose. The artifact
    # detector asks git which of those rules exclude a tracked file, so a fixture
    # repo without them would pass by omission rather than by working.
    (repo / ".gitignore").write_text(
        (REPO_ROOT / ".gitignore").read_text(encoding="utf-8"), encoding="utf-8"
    )
    return repo


def _commit(repo: Path, relative: str, body: str, *, force: bool = False) -> str:
    """Write and commit one file so it is tracked, the only state that counts.

    `force` builds the scenario the ignore rules cannot catch: with it, `git add`
    is refused outright, which is the first wall working as intended. `-f` walks
    past that wall, and the scanner is the second one.
    """
    target = repo / relative
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    subprocess.run(["git", "add", *(["-f"] if force else []), "--", relative], cwd=repo, check=True)
    subprocess.run(
        ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid",
         "commit", "-q", "-m", "fixture"],
        cwd=repo,
        check=True,
    )
    return relative


def _detectors(findings, path: str) -> set[str]:
    return {f.detector for f in findings if f.path == path}


def test_a_forced_added_ticket_export_is_flagged(scanner, fixture_repo: Path) -> None:
    """The R5 target: the export the backfill script writes, committed anyway.

    Measured while writing this: a plain `git add data/occ_tickets.json` is
    already refused, because the pre-existing `/data/` rule at `.gitignore:94`
    covers that directory. So the ordinary path is closed, and the case worth
    guarding is the forced add and the renamed export.
    """
    path = _commit(fixture_repo, "data/occ_tickets.json", f"{{{TICKET_LINE}\n}}", force=True)
    findings = scanner.scan_repo(fixture_repo)
    assert "tracked-customer-artifact" in _detectors(findings, path), findings


def test_an_internal_note_carrying_a_customer_email_is_flagged(
    scanner, fixture_repo: Path
) -> None:
    """The incident shape, away from any artifact path.

    372 `[internal]` notes of which 188 also carry an email is what ADR 0031
    measured on the corpus. Neither half is ambiguous on its own -- every repo
    file has email-shaped strings and the marker is defined in nine places --
    so the signal is the two on one line.
    """
    path = _commit(fixture_repo, "docs/notes.md", f"- {TICKET_LINE}\n")
    findings = scanner.scan_repo(fixture_repo)
    assert "internal-note-with-email" in _detectors(findings, path), findings


def test_company_registration_and_vat_shapes_are_flagged(
    scanner, fixture_repo: Path
) -> None:
    """A client company's own registry numbers are disclosure too (DIG-1498)."""
    path = _commit(fixture_repo, "docs/vendor.md", f"{REGISTRATION_LINE}\n")
    detectors = _detectors(scanner.scan_repo(fixture_repo), path)
    assert "company-registration" in detectors, detectors
    assert "vat-id" in detectors, detectors


def test_an_ordinary_source_file_passes(scanner, fixture_repo: Path) -> None:
    """The false-positive guard, stated as an assertion.

    Maintainer and vendor contact addresses are ordinary in this repo and are
    not customer PII. A scanner that flags them is a scanner that gets deleted.
    """
    path = _commit(
        fixture_repo,
        "apps/web/contact.ts",
        'export const SUPPORT = "support@example.com";\n'
        'export const SALES = "sales@example.com";\n',
    )
    assert scanner.scan_repo(fixture_repo) == []


def test_this_repository_is_clean(scanner) -> None:
    """The assertion that makes the CI job worth having.

    Scoped to a named commit: this is the tracked tree of the checkout under
    test, not production data and not any other branch.
    """
    findings = scanner.scan_repo(REPO_ROOT)
    assert findings == [], "\n".join(scanner.render(findings))


def test_a_finding_never_carries_the_matched_value(scanner, fixture_repo: Path) -> None:
    """The report names where, never what. A CI log is a public artifact."""
    path = _commit(fixture_repo, "docs/leak.md", f"{TICKET_LINE}\n{REGISTRATION_LINE}\n")
    findings = scanner.scan_repo(fixture_repo)
    assert findings, "fixture must produce findings for this test to mean anything"
    rendered = "\n".join(scanner.render(findings))
    for secret in ("jane.doe@kunde-beispiel.de", "HRB 12345", "DE123456789"):
        assert secret not in rendered, f"report leaked {secret!r}:\n{rendered}"
    assert path in rendered


# Each allowlisted detector's own pattern, so the drift test below can ask the
# real question -- does the entry still contain the shape it is exempt for --
# instead of hard-coding a literal per detector.
_DETECTOR_PATTERNS = {
    "internal-marker": "INTERNAL_MARKER_PATTERN",
    "company-registration": "REGISTRATION_PATTERN",
    "vat-id": "VAT_ID_PATTERN",
}


def test_the_allowlist_is_the_measured_one(scanner) -> None:
    """Every allowlisted path still carries the shape it is exempt for.

    `[internal]` is a convention the repo both defines and tests, and `HRB` /
    `Amtsgericht` / a VAT id have to be spelled out in the detector that finds
    them, so some allowlisting is unavoidable. What must not happen silently is
    a list growing until real notes are exempt. So every entry is required to
    still trip its own detector: remove the marker from a file and the exemption
    has outlived its reason, and the test says so.
    """
    for detector, entries in scanner.DETECTOR_ALLOWLIST.items():
        pattern = getattr(scanner, _DETECTOR_PATTERNS[detector])
        for path in sorted(entries):
            target = REPO_ROOT / path
            assert target.is_file(), f"{detector} allowlist entry gone: {path}"
            text = target.read_text(encoding="utf-8", errors="replace")
            assert pattern.search(text), (
                f"{path} no longer contains the {detector} shape it is "
                f"allowlisted for; drop the entry"
            )


def test_the_allowlist_does_not_exempt_the_compound_detector(scanner, fixture_repo: Path) -> None:
    """An allowlisted path is exempt from the bare marker, not from a real leak.

    The nine allowlisted files are exempt because they define or assert the
    marker. One of them carrying an `[internal]` note *with an email* is the
    incident, and the allowlist must not cover it.
    """
    allowlisted = scanner.INTERNAL_MARKER_ALLOWLIST[0]
    _commit(fixture_repo, allowlisted, f"{TICKET_LINE}\n")
    findings = scanner.scan_repo(fixture_repo)
    assert "internal-note-with-email" in _detectors(findings, allowlisted), findings


def test_a_registry_allowlist_is_not_a_blanket_exemption(scanner, fixture_repo: Path) -> None:
    """`DETECTOR_ALLOWLIST` is keyed by detector, so the self-exempt files stay
    inside the compound detector.

    `scripts/scan_customer_pii.py` and its suite are exempt from the two registry
    detectors because they must spell those shapes out. A blanket file exemption
    would also exempt them from the compound detector, and an unmasked note
    dropped into either file would go unremarked -- which is the incident this
    scanner exists for, in the one file that knows how to hide it.
    """
    for self_referential in sorted(scanner.SELF_REFERENTIAL_FILES):
        _commit(fixture_repo, self_referential, f"{TICKET_LINE}\n")
        findings = scanner.scan_repo(fixture_repo)
        detectors = _detectors(findings, self_referential)
        assert "internal-note-with-email" in detectors, (self_referential, findings)


def test_the_scanner_reuses_the_digitrace_patterns(scanner) -> None:
    """The plan requires the existing regex set, not a second invented one.

    Asserted by object identity against digitrace's own module: a hand-rolled
    copy of the email regex would pass any behavioural test and drift the day
    digitrace tightens its own.
    """
    sys.path.insert(0, str(REPO_ROOT / "digitrace" / "src"))
    from digitrace.redaction import EMAIL_PATTERN

    assert scanner.EMAIL_PATTERN is EMAIL_PATTERN


def test_the_email_shape_actually_fires(scanner) -> None:
    """Positive control on the reused pattern.

    A regex that silently matches nothing makes every other assertion in this
    file pass for the wrong reason.
    """
    assert scanner.EMAIL_PATTERN.search("someone@example.invalid")
    assert not scanner.EMAIL_PATTERN.search("not-an-address")


def test_the_cli_exits_nonzero_on_findings_and_zero_when_clean(
    scanner, fixture_repo: Path
) -> None:
    """CI reads the exit code; the report is the human affordance."""
    clean = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_customer_pii.py"),
         "--repo-root", str(fixture_repo)],
        capture_output=True, text=True, check=False,
    )
    assert clean.returncode == 0, clean.stdout + clean.stderr

    _commit(fixture_repo, "docs/leak.md", f"{TICKET_LINE}\n")
    report = fixture_repo / "report.json"
    dirty = subprocess.run(
        [sys.executable, str(REPO_ROOT / "scripts" / "scan_customer_pii.py"),
         "--repo-root", str(fixture_repo), "--json", str(report)],
        capture_output=True, text=True, check=False,
    )
    assert dirty.returncode == 1, dirty.stdout + dirty.stderr
    findings = json.loads(report.read_text(encoding="utf-8"))
    assert [f["detector"] for f in findings] == ["internal-note-with-email"], findings
    assert findings[0]["path"] == "docs/leak.md" and findings[0]["line"] == 1, findings


# The paths each artifact rule is meant to catch, and the one it must not.
ARTIFACT_PROBES = (
    ("occ_tickets/", "occ_tickets/tickets.json", True),
    ("occ_tickets*.json", "occ_tickets.json", True),
    ("occ_tickets*.jsonl", "nested/dir/occ_tickets.jsonl", True),
    ("occ_tickets*.ndjson", "occ_tickets.ndjson", True),
    ("seed_occ_tickets*", "seed_occ_tickets.json", True),
    # A snapshot export whose name does NOT start with `occ_tickets`, which is
    # the only thing this rule adds: `occ_tickets_snapshot_2026.json` is already
    # caught by `occ_tickets*.json` above, so probing that name here would test
    # the wrong rule and pass whatever this one does.
    ("*_occ_tickets_snapshot*.json", "data/zammad_occ_tickets_snapshot_2026.json", True),
    # The real script that produces the artifact must stay committable: its name
    # contains `occ_tickets` but does not start with it.
    ("occ_tickets*.json", "scripts/index_occ_tickets.py", False),
)


def test_the_customer_artifact_rules_match_the_scanner(scanner) -> None:
    """The scanner's rules and `.gitignore` are one definition in two homes.

    They are written down twice because the scanner must match paths itself --
    `git check-ignore -v` reports only the winning rule, and `/data/` at
    `.gitignore:94` shadows the artifact rules for everything under `data/`. A
    rule added to one file and not the other would leave the scanner checking
    nothing while the suite stayed green.
    """
    ignore_lines = {
        line.strip()
        for line in (REPO_ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    }
    missing = [r for r in scanner.CUSTOMER_ARTIFACT_RULES if r not in ignore_lines]
    assert not missing, f"scanner rules absent from .gitignore: {missing}"

    matchers = scanner._artifact_matchers()
    for rule, path, should_match in ARTIFACT_PROBES:
        matched = any(m.search(path) for r, m in matchers if r == rule)
        assert matched is should_match, f"{rule!r} vs {path!r}: matched={matched}"


def test_every_artifact_rule_has_a_probe_that_matches(scanner) -> None:
    """Positive control on the matchers.

    A compiled pattern that never fires would satisfy every `should_match: False`
    row above vacuously and guard nothing, so each rule must be shown catching a
    real path.
    """
    covered = {rule for rule, _path, should_match in ARTIFACT_PROBES if should_match}
    uncovered = [r for r in scanner.CUSTOMER_ARTIFACT_RULES if r not in covered]
    assert not uncovered, f"artifact rules with no firing probe: {uncovered}"
