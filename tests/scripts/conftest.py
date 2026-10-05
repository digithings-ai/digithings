"""Shared fixtures for tests/scripts/."""

from __future__ import annotations

import json
import os
import stat
from collections.abc import Callable, Sequence
from pathlib import Path
from typing import Any

import pytest

#: Cloudflare credential env vars — shared definition in tests.digi_test_env.
#: Re-export the autouse fixture so it remains active for this suite; rationale
#: for clearing (host-shell wrangler credentials leaking into d1_sync /
#: vectorize_sync tests) is documented there.
from tests.digi_test_env import (  # noqa: F401
    clear_cloudflare_credential_env as _clear_cloudflare_credential_env,
)

_STUB = '''#!/usr/bin/env python3
"""Rule-driven `gh` stand-in. First matching rule wins."""
import json, os, re, sys
from pathlib import Path

home = Path(os.environ["GH_STUB_DIR"])
cfg = json.loads((home / "config.json").read_text(encoding="utf-8"))
argv = sys.argv[1:]
with (home / "calls.jsonl").open("a", encoding="utf-8") as fh:
    fh.write(json.dumps(argv) + "\\n")

for rule in cfg["rules"]:
    if not re.search(rule["match"], " ".join(argv)):
        continue
    if "stdout" in rule:
        sys.stdout.write(rule["stdout"] + "\\n")
    if "stdout_file" in rule:
        sys.stdout.write((home / rule["stdout_file"]).read_text(encoding="utf-8") + "\\n")
    # `stdout_files` is a queue consumed one entry per matching call, so a script
    # that must re-read sees a *different* answer the second time. Each gh call is
    # a fresh process, so the shortened list is written back for the next one.
    if rule.get("stdout_files"):
        remaining = list(rule["stdout_files"])
        sys.stdout.write((home / remaining.pop(0)).read_text(encoding="utf-8") + "\\n")
        rule["stdout_files"] = remaining
        (home / "config.json").write_text(json.dumps(cfg), encoding="utf-8")
    if rule.get("stderr"):
        sys.stderr.write(rule["stderr"] + "\\n")
    sys.exit(rule.get("exit", 0))

sys.stderr.write("gh stub: no rule matched " + " ".join(argv) + "\\n")
sys.exit(97)
'''

#: Exit code the stub uses when nothing matched. Distinct from any real `gh`
#: failure so a test can tell "the script asked for something the test did not
#: describe" from "the API refused".
STUB_NO_MATCH = 97


class GhStub:
    """A `gh` on PATH that answers from a rule list, and records every call."""

    def __init__(self, root: Path) -> None:
        self._root = root

    @property
    def calls(self) -> list[list[str]]:
        """Every argv the script under test passed, in order."""
        log = self._root / "calls.jsonl"
        if not log.exists():
            return []
        return [json.loads(line) for line in log.read_text(encoding="utf-8").splitlines() if line]

    def matching(self, needle: str) -> list[list[str]]:
        """The subset of calls whose joined argv mentions `needle`."""
        return [call for call in self.calls if needle in " ".join(call)]

    def wrote(self, filename: str, content: str) -> None:
        """Seed a response body as a file, for payloads too big to inline."""
        (self._root / filename).write_text(content, encoding="utf-8")

    def set_rules(self, *rules: dict[str, Any]) -> None:
        """Swap the rule list on an existing stub.

        Needed when a script must see a *different* answer on its second call —
        that is how the re-read-after-merge behaviour gets tested at all.
        """
        (self._root / "config.json").write_text(
            json.dumps({"rules": list(rules)}), encoding="utf-8"
        )


def gh_rule(
    match: str,
    *,
    stdout: str | Sequence[Any] | None = None,
    stdout_file: str | None = None,
    stdout_files: Sequence[str] | None = None,
    stderr: str | None = None,
    exit_code: int = 0,
) -> dict[str, Any]:
    """One `gh` stub rule. `stdout` takes a str or any JSON-serialisable value.

    `match` is a regex searched against the joined argv, so `r"^pr merge 42 "`
    pins one merge and `r"merge_queue|merge-queue"` covers both spellings.
    `stdout_files` names a sequence of bodies served one per matching call, which
    is how a test says "the first read says this, the second read says that".
    """
    rule: dict[str, Any] = {"match": match}
    if stdout is not None:
        rule["stdout"] = stdout if isinstance(stdout, str) else json.dumps(stdout)
    if stdout_file is not None:
        rule["stdout_file"] = stdout_file
    if stdout_files is not None:
        rule["stdout_files"] = list(stdout_files)
    if stderr is not None:
        rule["stderr"] = stderr
    rule["exit"] = exit_code
    return rule


@pytest.fixture
def gh_stub(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Callable[..., GhStub]:
    """Install a rule-driven `gh` stub at the front of PATH for one test.

    Call it with the rules the script under test should see, in dispatch order::

        stub = gh_stub(
            gh_rule(r"^pr list", stdout=[pr]),
            gh_rule(r"^pr merge", stdout=""),
        )
        assert stub.matching("pr merge 42")

    Not autouse on purpose. A test exercising a script that shells out to `gh`
    *without* this stub reaches the real API with whatever credential the
    developer shell holds — the failure mode
    `tests/scripts/test_worktree_task_base_ref.py` warns about in its docstring.
    """
    root = tmp_path / "ghstub"
    bin_dir = root / "bin"
    bin_dir.mkdir(parents=True)
    stub = bin_dir / "gh"
    stub.write_text(_STUB, encoding="utf-8")
    stub.chmod(stub.stat().st_mode | stat.S_IEXEC | stat.S_IXGRP | stat.S_IXOTH)
    monkeypatch.setenv("GH_STUB_DIR", str(root))

    def _install(*rules: dict[str, Any]) -> GhStub:
        stub = GhStub(root)
        stub.set_rules(*rules)
        # Prepended, not replaced: a test may still need python, git or a real
        # binary for something the stub does not model.
        monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ.get('PATH', '')}")
        return stub

    return _install
