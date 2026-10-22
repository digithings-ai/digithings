"""The `dt` CLI's contract-error path (DIG-4911).

`scripts/dt` reads the local stack's contract files. A contract file that is
neither readable YAML nor JSON is a file the operator has to fix, so the CLI
names the file, says so on stderr and exits 1.

What it must never do is let the parser's own exception out of the command: a
traceback is not an answer, and the exit code a caller reads would be a crash
rather than a refusal. It must never fall back to the built-in catalogue
either - a contract that cannot be read is not a contract that was absent.

Both catches are pinned here. Deleting either
``except contracts.ContractParseError`` in ``scripts/dt`` leaves the rest of
the suite green, so the arms below are the only evidence that the path is
still there.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.localstack import contracts  # noqa: E402

#: A contract file that is neither YAML nor JSON: the flow sequence is never
#: closed, so the YAML reader refuses it and the JSON reader refuses it too.
BROKEN_CONTRACT = """\
services:
  - name: digigraph
    port: [8000
"""

#: The same file, readable. The control arm: the two differ only in the file,
#: so the error path is what the malformed file buys and nothing else.
READABLE_CONTRACT = """\
services:
  - name: digigraph
    port: 8000
"""


def _load_dt() -> object:
    """Load ``scripts/dt`` in-process: the file has no ``.py`` extension."""
    loader = importlib.machinery.SourceFileLoader("dt_contract_error_cli", str(REPO / "scripts/dt"))
    spec = importlib.util.spec_from_loader("dt_contract_error_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # A module executed without being registered first breaks the dataclass
    # machinery of its imports, which reads exactly like a defect in the file
    # under test.
    sys.modules["dt_contract_error_cli"] = module
    loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def dt() -> object:
    """The `dt` CLI, loaded once."""
    return _load_dt()


def _root_with_contract(tmp_path: Path, body: str) -> Path:
    """A repository root whose contract file carries ``body``."""
    contract = tmp_path / "config" / "contract" / "services.yaml"
    contract.parent.mkdir(parents=True, exist_ok=True)
    contract.write_text(body, encoding="utf-8")
    return tmp_path


@pytest.fixture()
def broken_root(tmp_path: Path) -> Path:
    """A root whose contract file cannot be parsed."""
    return _root_with_contract(tmp_path, BROKEN_CONTRACT)


@pytest.fixture()
def dt_at_broken_contract(dt: object, broken_root: Path, monkeypatch: pytest.MonkeyPatch) -> object:
    """`dt` reading a root whose contract file cannot be parsed."""
    monkeypatch.setattr(dt, "repo_root", lambda: broken_root)
    # A usable port knob, so the local defaults stay quiet and the only thing
    # on stderr is the contract error.
    monkeypatch.setenv("DT_SUPABASE_PORT", "55321")
    return dt


# --------------------------------------------------------------------------
# the refusal itself
# --------------------------------------------------------------------------


def test_a_contract_that_is_neither_yaml_nor_json_is_refused(broken_root: Path) -> None:
    """The catalogue refuses the file: it never guesses at a catalogue."""
    with pytest.raises(contracts.ContractParseError) as excinfo:
        contracts.load_checks(broken_root)
    assert "services.yaml" in str(excinfo.value)


# --------------------------------------------------------------------------
# `dt status` and `dt urls` report it and exit 1
# --------------------------------------------------------------------------


def test_status_names_the_contract_file_it_cannot_read(
    dt_at_broken_contract: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dt status` reports the file and exits 1: no traceback, no fallback."""
    assert dt_at_broken_contract.main(["status"]) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert "contract error:" in captured.err
    assert "services.yaml" in captured.err
    assert "Traceback" not in captured.err
    # Nothing on stdout: the command did not fall back to the built-in
    # catalogue and did not print a gate table.
    assert captured.out == ""


def test_urls_names_the_contract_file_it_cannot_read(
    dt_at_broken_contract: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """`dt urls` reports the file and exits 1: no traceback, no fallback."""
    assert dt_at_broken_contract.main(["urls"]) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert "contract error:" in captured.err
    assert "services.yaml" in captured.err
    assert "Traceback" not in captured.err
    assert captured.out == ""


def test_the_contract_error_is_json_when_asked(
    dt_at_broken_contract: object, capsys: pytest.CaptureFixture[str]
) -> None:
    """`--json` reports the same refusal as machine-readable output."""
    assert dt_at_broken_contract.main(["status", "--json"]) == 1  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    payload = json.loads(captured.out)
    assert payload["ok"] is False
    assert "services.yaml" in payload["error"]


# --------------------------------------------------------------------------
# the control arm: the same root, a readable contract, no refusal
# --------------------------------------------------------------------------


def test_a_readable_contract_still_produces_the_url_table(
    dt: object, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The error path is the malformed file, not the root the CLI reads.

    Without this arm the two refusal tests could pass for the wrong reason: a
    root the CLI cannot read at all would refuse just as loudly.
    """
    root = _root_with_contract(tmp_path, READABLE_CONTRACT)
    monkeypatch.setattr(dt, "repo_root", lambda: root)
    monkeypatch.setenv("DT_SUPABASE_PORT", "55321")
    assert dt.main(["urls"]) == 0  # type: ignore[attr-defined]
    captured = capsys.readouterr()
    assert "digigraph" in captured.out
    assert "contract error:" not in captured.err
