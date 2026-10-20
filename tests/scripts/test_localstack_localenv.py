"""The root .env is the operator's file (DIG-4662).

``dt up`` renders ``.dev.vars`` from the config contract and then rewrites the
root ``.env`` that docker compose reads. Before DIG-4662 the rewrite rebuilt
the file from the render alone, so every operator value in it - the ones
``docs/SELF_HOST.md`` 7.1 documents - was dropped on the next bring-up. The
repro was one line: put ``FOO=bar`` in the root ``.env``, run ``dt up``, and
``FOO`` was gone.

The rule now: the render is the base, the operator's values are kept, and the
local overrides win over both. Which of the first two a value came from is
remembered in a managed block at the bottom of the same file: it travels with
the values it describes, so a stale record cannot freeze a rotated secret.
"""

from __future__ import annotations

import json
import re
import stat
import subprocess
from pathlib import Path

import pytest

from scripts.localstack import localenv

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]

#: The port knob, pinned so the rendered values are deterministic.
ENV = {"DT_SUPABASE_PORT": "55321"}


def _root(tmp_path: Path, dev_vars: str = "", env: str = "") -> Path:
    """A checkout with a rendered .dev.vars and an operator .env."""
    root = tmp_path / "stack"
    root.mkdir()
    (root / ".dev.vars").write_text(dev_vars)
    (root / ".env").write_text(env)
    return root


def _values(root: Path) -> dict:
    return localenv.read_env_file(root / ".env")


def _block(root: Path) -> str:
    """The managed provenance block, as it sits in the .env."""
    for line in (root / ".env").read_text().splitlines():
        if line.strip().startswith(localenv.STATE_MARKER):
            return line
    raise AssertionError("the .env carries no provenance block")


def _state(root: Path) -> dict:
    """The managed provenance block, parsed."""
    for line in (root / ".env").read_text().splitlines():
        stripped = line.strip()
        if stripped.startswith(localenv.STATE_MARKER):
            return json.loads(stripped[len(localenv.STATE_MARKER) :].strip())
    raise AssertionError("the .env carries no provenance block")


def _replace(root: Path, name: str, old: str, new: str) -> None:
    body = (root / ".env").read_text().replace(f"{name}={old}", f"{name}={new}")
    (root / ".env").write_text(body)


def _strip_block(root: Path) -> None:
    """Take the managed provenance block out of the .env, as an operator would."""
    lines = (root / ".env").read_text().splitlines()
    kept = [
        line
        for line in lines
        if not line.startswith(localenv.STATE_HEADER)
        and not line.strip().startswith(localenv.STATE_MARKER)
    ]
    (root / ".env").write_text("".join(f"{line}\n" for line in kept))


def test_an_operator_value_survives_a_bring_up(tmp_path: Path) -> None:
    """The repro: FOO=bar in the root .env, dt up, FOO is still there."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n", env="FOO=bar\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["FOO"] == "bar"


def test_the_rendered_values_still_land(tmp_path: Path) -> None:
    """The render is still the base of the file."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "rendered"


def test_the_local_values_still_win(tmp_path: Path) -> None:
    """SELF_HOST.md 7.1: the local digikey DSN always wins over the rendered one."""
    root = _root(
        tmp_path,
        dev_vars="DIGIKEY_DATABASE_URL=postgres://shared/db\n",
        env="DIGIKEY_DATABASE_URL=postgres://operator/db\n",
    )
    localenv.write_env(root, env=ENV)
    assert _values(root)["DIGIKEY_DATABASE_URL"] == localenv.LOCAL_DIGIKEY_DATABASE_URL


def test_the_omniroute_password_stays_stable(tmp_path: Path) -> None:
    """The guard and omniroute read the same .env, so the value cannot move."""
    root = _root(tmp_path)
    localenv.write_env(root, env=ENV)
    first = _values(root)["OMNIROUTE_AUTH_PASSWORD"]
    localenv.write_env(root, env=ENV)
    second = _values(root)["OMNIROUTE_AUTH_PASSWORD"]
    assert first
    assert first == second


def test_the_operator_value_for_a_rendered_key_survives(tmp_path: Path) -> None:
    """LITELLM_MASTER_KEY is both in the render and in SELF_HOST.md 7.1."""
    root = _root(tmp_path, dev_vars="LITELLM_MASTER_KEY=rendered\n")
    localenv.write_env(root, env=ENV)
    _replace(root, "LITELLM_MASTER_KEY", "rendered", "operator")
    localenv.write_env(root, env=ENV)
    assert _values(root)["LITELLM_MASTER_KEY"] == "operator"


def test_a_refreshed_render_value_reaches_the_env(tmp_path: Path) -> None:
    """A rotated secret still lands when the operator did not touch it."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    (root / ".dev.vars").write_text("AUTH_SECRET=second\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "second"


def test_an_operator_edit_of_a_rendered_key_survives(tmp_path: Path) -> None:
    """An edit made after the render is the operator's own value."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    _replace(root, "AUTH_SECRET", "first", "mine")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "mine"


def test_a_rotated_secret_reaches_the_env_without_a_provenance_block(
    tmp_path: Path,
) -> None:
    """The review that found the freeze: a stale copy must not win.

    With no record of who wrote what, the render decides for the names it
    claims. A value that looks like the operator's could just as well be the
    previous render's value, and a stale secret in the .env is the one that
    breaks the stack.
    """
    root = _root(tmp_path, dev_vars="AUTH_SECRET=second\n", env="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "second"
    # And it keeps following the render: the first run cannot freeze it.
    (root / ".dev.vars").write_text("AUTH_SECRET=third\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "third"


def test_without_the_provenance_the_render_decides_for_the_names_it_claims(
    tmp_path: Path,
) -> None:
    """Losing the block leaves no room to tell an edit from a stale copy."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    _replace(root, "AUTH_SECRET", "first", "mine")
    _strip_block(root)
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "first"


def test_the_operator_own_name_survives_a_lost_provenance_block(tmp_path: Path) -> None:
    """A name the render does not claim is the operator's, record or no record."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n", env="FOO=bar\n")
    localenv.write_env(root, env=ENV)
    _strip_block(root)
    localenv.write_env(root, env=ENV)
    assert _values(root)["FOO"] == "bar"
    assert _values(root)["AUTH_SECRET"] == "first"


def test_a_rotated_secret_reaches_the_env_after_the_render_stopped_claiming_it(
    tmp_path: Path,
) -> None:
    """A name the render drops keeps the render's ownership of the value.

    The render claims AUTH_SECRET, then stops claiming it: the contract
    entry goes, or the render is asked for a subset. The value that stays in
    the .env is still the render's, so the record has to keep saying so. If
    it were relabelled as the operator's, the next render that claims the
    name again would find a value that reads as the operator's own and the
    rotated secret would never reach the .env.
    """
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    assert _state(root)["AUTH_SECRET"]["source"] == "render"

    # The render stops claiming the name.
    (root / ".dev.vars").write_text("")
    localenv.write_env(root, env=ENV)
    assert (
        _state(root)["AUTH_SECRET"]["source"] == "render"
    ), "the record must not hand a render's value to the operator"

    # And when the render claims it again, the rotated secret lands.
    (root / ".dev.vars").write_text("AUTH_SECRET=second\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "second"


def test_a_line_that_is_not_an_env_entry_is_not_carried_over(tmp_path: Path) -> None:
    """The host bring-up sources the .env under `set -e`.

    A line whose name is not an env identifier ("FOO BAR=baz") is not an
    entry: the shell reads it as a command and the bring-up aborts with
    "FOO: command not found". The rewrite before DIG-4662 dropped such
    lines, so this one does not carry them over either.
    """
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n", env="FOO BAR=baz\n")
    localenv.write_env(root, env=ENV)
    assert "FOO BAR" not in (root / ".env").read_text()
    assert _values(root)["AUTH_SECRET"] == "first"


def test_the_env_is_written_private(tmp_path: Path) -> None:
    """The .env holds secrets; it stays mode 0600."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n")
    localenv.write_env(root, env=ENV)
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600


def test_the_root_env_is_git_ignored() -> None:
    """The .env holds the operator's values; never commit it."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", ".env"],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 0, ".env is not git-ignored"


def test_the_provenance_block_carries_no_values(tmp_path: Path) -> None:
    """Only digests and names, never a secret."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n", env="FOO=bar\n")
    localenv.write_env(root, env=ENV)
    block = _block(root)
    assert "rendered" not in block
    assert "bar" not in block
    payload = json.loads(block.split(localenv.STATE_MARKER, 1)[1].strip())
    assert payload["AUTH_SECRET"]["source"] == "render"
    assert len(payload["AUTH_SECRET"]["digest"]) == 64


def test_the_provenance_describes_the_file_it_lives_in(tmp_path: Path) -> None:
    """The record and the values are written together, so they cannot drift."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n", env="FOO=bar\n")
    localenv.write_env(root, env=ENV)
    values = _values(root)
    for name, entry in localenv.read_state(root / ".env").items():
        assert entry["digest"] == localenv.digest(values[name]), name


def test_a_broken_provenance_block_does_not_stop_the_write(tmp_path: Path) -> None:
    """A truncated block is read as empty, not as a crash."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n", env="FOO=bar\n")
    localenv.write_env(root, env=ENV)
    body = (root / ".env").read_text()
    (root / ".env").write_text(body + f"{localenv.STATE_MARKER} {{not json\n")
    localenv.write_env(root, env=ENV)
    assert _values(root)["FOO"] == "bar"
    assert _values(root)["AUTH_SECRET"] == "rendered"


def test_the_compose_step_is_the_one_that_writes_the_env(tmp_path: Path) -> None:
    """The plan step still runs this module, so the fix is where it matters."""
    text = (REPO / "scripts" / "localstack" / "orchestrate.py").read_text()
    assert "scripts/localstack/localenv.py" in text


# ------------------------------------------ the digisearch monitor store (DIG-4661)


#: Paperclip's own board database port on this host.
BOARD_DB_PORT = 54329


def _compose_service_block(service: str) -> list[str]:
    """The lines of one compose service, so a scan cannot pick another's."""
    lines = (REPO / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
    for index, line in enumerate(lines):
        if line == f"  {service}:":
            block = []
            for candidate in lines[index + 1 :]:
                if re.match(r"^  \S", candidate):
                    break
                block.append(candidate)
            return block
    raise AssertionError(f"no {service} service in docker-compose.yml: the scan is void")


def _contract_monitors_template() -> str:
    """The canonical value the contract renders for the monitors store."""
    text = (REPO / "config" / "contract" / "secrets.yaml").read_text(encoding="utf-8")
    start = text.index("DIGISEARCH_MONITORS_DB")
    match = re.search(r'template:\s*"([^"]+)"', text[start:])
    assert match, "the contract no longer renders a template for the monitors store"
    return match.group(1)


def test_the_local_store_path_is_the_one_the_compose_service_uses():
    """The path has to follow the service, or the store stops persisting."""
    block = _compose_service_block("digisearch")
    workspace = [line.strip() for line in block if line.strip().startswith("- DIGI_WORKSPACE=")]
    assert len(workspace) == 1, f"expected one DIGI_WORKSPACE line, got {workspace}"
    store = (REPO / "digisearch" / "src" / "digisearch" / "monitors" / "store.py").read_text(
        encoding="utf-8"
    )
    directory = re.search(r'_WORKSPACE_DB_DIR\s*=\s*"([^"]+)"', store)
    filename = re.search(r'_DB_FILENAME\s*=\s*"([^"]+)"', store)
    assert directory and filename, "the monitor store constants moved: the scan is void"
    root = workspace[0].split("=", 1)[1].strip()
    expected = f"{root}/{directory.group(1)}/{filename.group(1)}"
    assert localenv.LOCAL_DIGISEARCH_MONITORS_DB == expected


def test_the_rendered_env_does_not_aim_the_monitors_store_at_the_board_database(
    tmp_path: Path,
):
    """The repro: the rendered .env carried 127.0.0.1:54329."""
    (tmp_path / ".dev.vars").write_text(
        f"DIGISEARCH_MONITORS_DB={_contract_monitors_template()}\n", encoding="utf-8"
    )
    localenv.write_env(tmp_path, env=ENV)
    rendered = localenv.read_env_file(tmp_path / ".env")
    value = rendered["DIGISEARCH_MONITORS_DB"]
    assert str(BOARD_DB_PORT) not in value
    assert value == localenv.LOCAL_DIGISEARCH_MONITORS_DB


def test_the_local_override_wins_over_the_contract_value():
    overrides = localenv.local_overrides({}, {})
    assert overrides["DIGISEARCH_MONITORS_DB"] == localenv.LOCAL_DIGISEARCH_MONITORS_DB


def test_the_mcp_service_uses_the_same_monitor_store():
    """The .env is the env_file of every compose service.

    The digisearch-mcp service creates watches in the monitor store too, so it
    has to resolve the same store on the same volume: a store of its own would
    lose every watch on the next recreate and hide them from digisearch.
    """
    block = _compose_service_block("digisearch-mcp")
    workspace = [line.strip() for line in block if line.strip().startswith("- DIGI_WORKSPACE=")]
    assert workspace == ["- DIGI_WORKSPACE=/data/monitors"], workspace
    volumes = [line.strip() for line in block if line.strip().startswith("- digisearch_monitors:")]
    assert volumes == ["- digisearch_monitors:/data/monitors"], volumes
