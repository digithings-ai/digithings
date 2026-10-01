"""history --copy-last copies the latest dict transcript to the clipboard."""

from __future__ import annotations

from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.history import append_entry, dict_entry, speak_entry

from tests.dvo.fakes import FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit


def test_copy_last_uses_pbcopy_on_darwin(tmp_path: Path) -> None:
    append_entry(tmp_path / "history.jsonl", dict_entry("first", None))
    append_entry(tmp_path / "history.jsonl", speak_entry("spoken"))
    append_entry(tmp_path / "history.jsonl", dict_entry("latest dict", None))
    runner = FakeRunner({"pbcopy": FakeReply()})
    runtime = Runtime(
        platform="darwin",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands={"pbcopy": "/usr/bin/pbcopy"}),
        runner=runner,
    )
    result = run(["history", "--copy-last"], runtime)
    assert result.code == 0
    assert result.stdout == "latest dict\n"
    assert "copied" in result.stderr
    call = runner.call_for("pbcopy")
    assert call is not None
    assert call.stdin == "latest dict"


def test_copy_last_empty_history_fails(tmp_path: Path) -> None:
    runtime = Runtime(
        platform="darwin",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(commands={"pbcopy": "/usr/bin/pbcopy"}),
        runner=FakeRunner(),
    )
    result = run(["history", "--copy-last"], runtime)
    assert result.code == 1
    assert "no dict entry" in result.stderr


def test_history_json_output(tmp_path: Path) -> None:
    append_entry(tmp_path / "history.jsonl", dict_entry("alpha", None))
    runtime = Runtime(
        platform="linux",
        home=tmp_path,
        env={"DIGIVOICE_DATA_DIR": str(tmp_path)},
        probe=FakeProbe(),
    )
    result = run(["history", "--json", "--last", "1"], runtime)
    assert result.code == 0
    assert '"kind": "dict"' in result.stdout
    assert "alpha" in result.stdout
