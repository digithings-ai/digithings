"""Pin scripts/forgejo-branch-protection-verify.sh profiles.

The verifier runs against a fake Forgejo API on 127.0.0.1 with a throwaway env
file, so no real forge or token is involved. ``strict`` and ``light`` must keep
expecting ``require_signed_commits: false`` (the exempt mirrored branches);
``strict-signed`` and ``light-signed`` are the same profiles with it true.
"""

from __future__ import annotations

import json
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "forgejo-branch-protection-verify.sh"

STRICT = {
    "enable_push": False,
    "required_approvals": 1,
    "enable_status_check": True,
    "require_signed_commits": False,
    "apply_to_admins": True,
    "block_on_rejected_reviews": True,
    "dismiss_stale_approvals": True,
    "block_on_outdated_branch": True,
    "status_check_contexts": ["ci/woodpecker/pr/woodpecker"],
}
LIGHT = {
    "enable_push": False,
    "required_approvals": 1,
    "enable_status_check": False,
    "require_signed_commits": False,
    "apply_to_admins": True,
    "block_on_rejected_reviews": True,
    "dismiss_stale_approvals": False,
    "block_on_outdated_branch": False,
    "status_check_contexts": [],
}


def _signed(rule: dict) -> dict:
    return {**rule, "require_signed_commits": True}


def _serve(rules: dict[str, list[dict]]):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            if self.headers.get("Authorization") != "token fake-test-token":
                self.send_response(401)
                self.end_headers()
                return
            parts = self.path.strip("/").split("/")
            # api/v1/repos/<owner>/<repo>/branch_protections
            repo = parts[4] if len(parts) == 6 else ""
            if repo not in rules:
                self.send_response(404)
                self.end_headers()
                return
            body = json.dumps(rules[repo]).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    server = HTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def _run(
    tmp_path: Path, rules: dict[str, list[dict]], inventory: str
) -> subprocess.CompletedProcess:
    server = _serve(rules)
    try:
        env_file = tmp_path / "local-forge.env"
        env_file.write_text(
            f"FORGEJO_URL=http://127.0.0.1:{server.server_port}\n"
            "FORGEJO_TOKEN=fake-test-token\n"
            f"FORGEJO_PROTECTED_REPOS={inventory}\n",
            encoding="utf-8",
        )
        return subprocess.run(
            ["bash", str(SCRIPT)],
            env={"PATH": "/usr/bin:/bin:/usr/local/bin", "LOCAL_FORGE_ENV": str(env_file)},
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
    finally:
        server.shutdown()


def _rules(repo_rules: dict[str, dict[str, dict]]) -> dict[str, list[dict]]:
    return {
        repo: [{"rule_name": name, **rule} for name, rule in branches.items()]
        for repo, branches in repo_rules.items()
    }


def test_unsigned_profiles_behave_as_before(tmp_path: Path) -> None:
    done = _run(
        tmp_path,
        _rules({"alpha": {"main": STRICT, "develop": LIGHT}}),
        "alpha:main:strict,alpha:develop:light",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "verification OK (2 rules across 1 repos)" in done.stdout


def test_unsigned_profiles_still_reject_a_signed_rule(tmp_path: Path) -> None:
    done = _run(
        tmp_path,
        _rules({"alpha": {"main": _signed(STRICT), "develop": _signed(LIGHT)}}),
        "alpha:main:strict,alpha:develop:light",
    )
    assert done.returncode == 1
    assert "MISMATCH alpha/main: require_signed_commits = True (expected False)" in done.stdout
    assert "MISMATCH alpha/develop: require_signed_commits = True (expected False)" in done.stdout
    assert done.stdout.count("MISMATCH") == 2


def test_signed_profiles_accept_signed_rules(tmp_path: Path) -> None:
    done = _run(
        tmp_path,
        _rules(
            {
                "alpha": {"main": STRICT, "develop": LIGHT},
                "beta": {"main": _signed(STRICT), "develop": _signed(LIGHT)},
            }
        ),
        "alpha:main:strict,alpha:develop:light,beta:main:strict-signed,beta:develop:light-signed",
    )
    assert done.returncode == 0, done.stdout + done.stderr
    assert "verification OK (4 rules across 2 repos)" in done.stdout


def test_signed_profiles_differ_only_in_the_signed_field(tmp_path: Path) -> None:
    done = _run(
        tmp_path,
        _rules({"beta": {"main": STRICT, "develop": LIGHT}}),
        "beta:main:strict-signed,beta:develop:light-signed",
    )
    assert done.returncode == 1
    mismatches = [line for line in done.stdout.splitlines() if line.startswith("MISMATCH")]
    assert mismatches == [
        "MISMATCH beta/main: require_signed_commits = False (expected True)",
        "MISMATCH beta/develop: require_signed_commits = False (expected True)",
    ]


def test_unknown_profile_still_fails_closed(tmp_path: Path) -> None:
    done = _run(tmp_path, _rules({"alpha": {"main": STRICT}}), "alpha:main:signed")
    assert done.returncode != 0
    assert "unknown profile 'signed'" in done.stdout + done.stderr


def test_missing_rule_is_still_a_failure(tmp_path: Path) -> None:
    done = _run(tmp_path, _rules({"alpha": {}}), "alpha:main:strict-signed")
    assert done.returncode == 1
    assert "MISSING alpha/main: no protection rule" in done.stdout
