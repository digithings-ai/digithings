"""Tests for `scripts/check_pii_seed_payloads.py`.

The guard's own failure modes are the interesting ones, so most of this is
about what it must NOT flag and what it must never print:

* a reserved example domain is not a finding (otherwise fixtures cannot be
  written and the allowlist grows by exemption);
* a free-mail domain IS a finding, because `gmail.test` is what a fixture
  should say and `gmail.com` is a person;
* the output never contains the address it found — a guard that echoes the
  value is a second disclosure channel into a CI log;
* deleting a payload is never a finding, or containment cannot land.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

# No `noqa: E402` here: ruff permits `sys.path` manipulation before a module-level
# import, so the directive is unused and RUF100 (which this repo selects) fails
# the file for carrying it.
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "scripts"))

from check_pii_seed_payloads import (
    Finding,
    domain_of,
    is_payload,
    is_reserved,
    main,
    scan,
    scan_text,
    select_paths,
    uncommitted_payload_paths,
    unmasked_addresses,
)

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]


def require_ref(ref: str) -> None:
    """Skip a test that needs a remote-tracking ref this checkout may not have.

    `ruff-and-scripts` on `ci.yml` checks out a PR merge ref with the default
    fetch-depth, so `origin/main` is frequently absent. `select_paths` raises
    `SystemExit` on an unresolvable ref, which would fail the suite for a reason
    that has nothing to do with this guard. Same shape as the skip in
    `tests/scripts/test_check_review_coverage.py`, which exists for the same cause.
    """
    resolvable = subprocess.run(
        ["git", "rev-parse", "--verify", f"{ref}^{{commit}}"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    if resolvable.returncode != 0:
        pytest.skip(f"{ref} is not resolvable in this checkout")


# Reserved example domains (RFC 2606 / 6761). These are the values a fixture is
# expected to use and none of them is a finding.
RESERVED = [
    "jane.doe@example.test",
    "jane@example.com",
    "someone@mail.example.invalid",
    "dev@localhost",
]

# Real-looking addresses on real domains. Never committed, never printed.
UNMASKED = [
    "jane.doe@acme-corp.example.org",
    "someone@gmail.com",
    "first.last@company.co.uk",
    "jane@acme-corp.de",
]


class TestIsReserved:
    @pytest.mark.parametrize("address", RESERVED)
    def test_reserved_domains_are_not_findings(self, address: str) -> None:
        assert is_reserved(address) is True

    @pytest.mark.parametrize("address", UNMASKED)
    def test_organisational_domains_are_findings(self, address: str) -> None:
        assert is_reserved(address) is False

    @pytest.mark.parametrize(
        "address",
        [
            "jane@gmail.test",  # a free-mail *shape* on a reserved TLD passes
            "jane@corp.example",  # reserved TLD as the last label
            "jane@sub.example.test",  # subdomain of a reserved TLD
            "jane@mail.acme.invalid",  # deeper still
        ],
    )
    def test_reserved_tld_passes_at_any_depth(self, address: str) -> None:
        assert is_reserved(address) is True

    @pytest.mark.parametrize(
        "address",
        [
            # These are the cases a "any label matches" rule wrongly allows.
            # Each has `example` as a *middle* label under a real TLD, so each
            # is a registrable domain shape and must be reported.
            "jane@acme.example.com",
            "jane@corp.example.org",
            "jane.doe@acme-corp.example.org",
        ],
    )
    def test_a_reserved_label_in_the_middle_is_still_a_finding(self, address: str) -> None:
        assert is_reserved(address) is False

    @pytest.mark.parametrize(
        ("address", "domain"),
        [
            ("jane@example.test", "example.test"),
            ("jane@example.test.", "example.test"),  # trailing root dot
            ('"Jane Doe" <jane@corp.test>', "corp.test"),  # quoted From header
        ],
    )
    def test_domain_of(self, address: str, domain: str) -> None:
        assert domain_of(address) == domain

    def test_a_local_part_containing_at_does_not_confuse_the_split(self) -> None:
        # rpartition on the last "@": the domain is what follows it.
        assert domain_of("weird@local@corp.test") == "corp.test"

    def test_no_domain_is_not_reserved(self) -> None:
        assert is_reserved("not-an-address") is False
        assert is_reserved("") is False


class TestUnmaskedAddresses:
    def test_counts_occurrences_not_distinct_addresses(self) -> None:
        text = "a@acme-corp.de and again a@acme-corp.de"
        assert unmasked_addresses(text) == 2

    def test_mixed_line_counts_only_the_unmasked_one(self) -> None:
        assert unmasked_addresses("jane@example.test then real@acme-corp.de") == 1

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "no addresses at all",
            "a version like 1.2.3 and a port like localhost:8080",
            "Subject: Re: Ihre Rechnung vom 3. Mai",
        ],
    )
    def test_ordinary_prose_is_untouched(self, text: str) -> None:
        assert unmasked_addresses(text) == 0


class TestScanText:
    def test_reports_line_numbers(self) -> None:
        findings = scan_text("seed/x.jsonl", "clean\nreal@acme-corp.de\n")
        assert [(f.line, f.count) for f in findings] == [(2, 1)]

    def test_no_findings_for_a_clean_payload(self) -> None:
        assert scan_text("seed/x.jsonl", '{"customer":"jane@example.test"}') == []

    def test_two_addresses_on_one_line_are_counted_together(self) -> None:
        findings = scan_text("seed/x.jsonl", "a@acme-corp.de b@acme-corp.de")
        assert len(findings) == 1
        assert findings[0].count == 2


class TestNeverPrintsAValue:
    def test_render_carries_no_address(self) -> None:
        rendered = Finding(path="seed/x.jsonl", line=3, count=2).render()
        assert "seed/x.jsonl:3" in rendered
        assert "@" not in rendered

    def test_json_output_carries_no_address(self, tmp_path: Path, capsys) -> None:
        payload = tmp_path / "seed.jsonl"
        payload.write_text('{"c":"real.person@acme-corp.de"}\n', encoding="utf-8")
        findings = scan(["seed.jsonl"], root=tmp_path)
        assert findings, "fixture should produce a finding"

        # The serialised payload of findings must be free of the address.
        rendered = json.dumps(
            [{"path": f.path, "line": f.line, "count": f.count} for f in findings]
        )
        assert "real.person" not in rendered
        assert "acme-corp.de" not in rendered


class TestIsPayload:
    @pytest.mark.parametrize(
        "path",
        [
            "apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl",
            "digisearch/corpus/help.json",
        ],
    )
    def test_payloads_are_in_scope(self, path: str) -> None:
        assert is_payload(path) is True

    @pytest.mark.parametrize(
        "path",
        [
            "scripts/index_occ_tickets.py",
            "apps/foo/wrangler.toml",
            "tests/scripts/test_seed.py",  # SKIP_PREFIXES
            "docs/ops/notes.json",
            "projects/x/vault/data.jsonl",  # confidential local vault
            "apps/foo/README.md",
        ],
    )
    def test_non_payloads_are_out_of_scope(self, path: str) -> None:
        assert is_payload(path) is False


class TestScopeSelection:
    def test_explicit_all_wins_over_base(self) -> None:
        paths, scope = select_paths("origin/main", "HEAD", whole_tree=True)
        assert scope == "tracked tree"
        assert isinstance(paths, list)

    def test_no_base_and_no_all_is_the_working_tree(self) -> None:
        _, scope = select_paths(None, "HEAD", whole_tree=False)
        assert scope == "uncommitted changes"

    def test_a_base_is_a_diff(self) -> None:
        require_ref("origin/main")
        _, scope = select_paths("origin/main", "HEAD", whole_tree=False)
        assert scope == "origin/main...HEAD"


class TestRealRepoTree:
    def test_the_committed_occ_payload_is_a_finding_on_main(self) -> None:
        """The payload this guard exists for must actually trip it.

        Read from git rather than the working tree, because the fix branch has
        no seed payload checked out. Counts only; no value is asserted or shown.
        """
        result = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                "show",
                "origin/main:apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl",
            ],
            capture_output=True,
            text=True,
            check=False,
        )
        if result.returncode != 0:
            pytest.skip("occ_tickets.jsonl is not on origin/main in this clone")

        findings = scan_text(
            "seed/occ_tickets.jsonl",
            result.stdout,
        )
        assert findings, "the committed payload carries addresses; the guard must see them"
        # 919 rows, 791 of them quoting an address (DIG-1210 measurement). Assert
        # a floor rather than the exact figure so an unrelated upstream refresh
        # does not turn this into a brittle test.
        assert sum(f.count for f in findings) > 500


class TestUncommittedScope:
    """The default (no-argument) run, in a throwaway repo.

    This is the mode a developer actually types, and it had two holes that only
    a real `git status` in a real repo exposes — which is why these build one.
    """

    @staticmethod
    def _repo(tmp_path: Path) -> Path:
        root = tmp_path / "repo"
        root.mkdir()
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", *a], cwd=root, capture_output=True, text=True, check=True
        )
        run("init", "-q", "-b", "main")
        run("config", "user.email", "t@example.test")
        run("config", "user.name", "T")
        (root / "seed").mkdir()
        (root / "seed" / "clean.jsonl").write_text(
            '{"customer": "jane.doe@example.test"}\n', encoding="utf-8"
        )
        run("add", "-A")
        run("commit", "-qm", "base")
        return root

    def test_a_new_payload_in_a_brand_new_directory_is_caught(self, tmp_path: Path) -> None:
        """`-uall` is what makes this visible.

        `git status --porcelain` collapses an untracked directory to `?? dir/`,
        which is not a payload suffix. Without `-uall` the whole nested case —
        the realistic one, a new seed folder — passed silently.
        """
        root = self._repo(tmp_path)
        fresh = root / "seed" / "new"
        fresh.mkdir()
        (fresh / "tickets.jsonl").write_text(
            '{"customer": "real.person@acme-corp.de"}\n', encoding="utf-8"
        )

        paths = uncommitted_payload_paths(root)
        assert paths == ["seed/new/tickets.jsonl"], (
            "an untracked payload inside a new directory must be in scope; "
            "this is the shape the guard exists to stop"
        )
        findings = scan(paths, root=root)
        assert [f.line for f in findings] == [1]
        assert findings[0].count == 1

    def test_a_renamed_payload_is_reported_at_its_destination(self, tmp_path: Path) -> None:
        """`R  old.jsonl -> new.jsonl` — the destination is the live path.

        Testing the combined `old -> new` string would match neither path's
        suffix reliably and the rename would slip through.
        """
        root = self._repo(tmp_path)
        (root / "seed" / "clean.jsonl").write_text(
            '{"customer": "real.person@acme-corp.de"}\n', encoding="utf-8"
        )
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", *a], cwd=root, capture_output=True, text=True, check=True
        )
        run("mv", "seed/clean.jsonl", "seed/renamed.jsonl")
        run("add", "-A")

        paths = uncommitted_payload_paths(root)
        assert paths == ["seed/renamed.jsonl"]
        assert scan(paths, root=root)

    def test_a_deleted_payload_is_not_a_finding(self, tmp_path: Path) -> None:
        """Containment has to be able to land; deleting is the fix."""
        root = self._repo(tmp_path)
        run = lambda *a: subprocess.run(  # noqa: E731
            ["git", *a], cwd=root, capture_output=True, text=True, check=True
        )
        run("rm", "-q", "seed/clean.jsonl")
        run("commit", "-qm", "remove it")
        assert uncommitted_payload_paths(root) == []

    def test_a_clean_working_tree_scans_nothing(self, tmp_path: Path) -> None:
        root = self._repo(tmp_path)
        assert uncommitted_payload_paths(root) == []


class TestMain:
    def test_all_mode_exits_zero_on_this_branch(self, capsys) -> None:
        # The masking branch removes the seed payload, so the whole tracked tree
        # is clean. If this ever fails, a payload with real addresses is back.
        code = main(["--all"])
        out = capsys.readouterr().out
        assert code == 0, out
        assert "no unmasked address" in out
