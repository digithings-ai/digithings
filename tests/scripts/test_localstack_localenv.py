"""The root .env is the operator's file (DIG-4662).

``dt up`` renders ``.dev.vars`` from the config contract and then rewrites the
root ``.env`` that docker compose reads. Before DIG-4662 the rewrite rebuilt
the file from the render alone, so every operator value in it - the ones
``docs/SELF_HOST.md`` 7.1 documents - was dropped on the next bring-up. The
repro was one line: put ``FOO=bar`` in the root ``.env``, run ``dt up``, and
``FOO`` was gone.

The rule now: the render is the base, the operator's values are kept, and the
local overrides win over both.
"""

from __future__ import annotations

import json
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


def _replace(root: Path, name: str, old: str, new: str) -> None:
    body = (root / ".env").read_text().replace(f"{name}={old}", f"{name}={new}")
    (root / ".env").write_text(body)


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
    root = _root(
        tmp_path,
        dev_vars="LITELLM_MASTER_KEY=rendered\n",
        env="LITELLM_MASTER_KEY=operator\n",
    )
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


def test_the_operator_value_survives_a_lost_state_file(tmp_path: Path) -> None:
    """The provenance record is a hint; losing it must not drop a value."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=first\n")
    localenv.write_env(root, env=ENV)
    _replace(root, "AUTH_SECRET", "first", "mine")
    (root / localenv.STATE_FILE).unlink()
    localenv.write_env(root, env=ENV)
    assert _values(root)["AUTH_SECRET"] == "mine"


def test_the_env_is_written_private(tmp_path: Path) -> None:
    """The .env holds secrets; it stays mode 0600."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n")
    localenv.write_env(root, env=ENV)
    assert stat.S_IMODE((root / ".env").stat().st_mode) == 0o600


def test_the_state_file_is_git_ignored(tmp_path: Path) -> None:
    """The sidecar carries digests of the operator's values; never commit it."""
    result = subprocess.run(
        ["git", "check-ignore", "-q", localenv.STATE_FILE],
        cwd=str(REPO),
        capture_output=True,
    )
    assert result.returncode == 0, f"{localenv.STATE_FILE} is not git-ignored"


def test_the_state_file_carries_no_values(tmp_path: Path) -> None:
    """Only digests and names, never a secret."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n")
    localenv.write_env(root, env=ENV)
    raw = (root / localenv.STATE_FILE).read_text()
    assert "rendered" not in raw
    payload = json.loads(raw)
    assert payload["AUTH_SECRET"]["source"] == "render"


def test_a_broken_state_file_does_not_stop_the_write(tmp_path: Path) -> None:
    """A truncated sidecar is read as empty, not as a crash."""
    root = _root(tmp_path, dev_vars="AUTH_SECRET=rendered\n", env="FOO=bar\n")
    (root / localenv.STATE_FILE).write_text("{not json")
    localenv.write_env(root, env=ENV)
    assert _values(root)["FOO"] == "bar"
    assert _values(root)["AUTH_SECRET"] == "rendered"


def test_the_compose_step_is_the_one_that_writes_the_env(tmp_path: Path) -> None:
    """The plan step still runs this module, so the fix is where it matters."""
    text = (REPO / "scripts" / "localstack" / "orchestrate.py").read_text()
    assert "scripts/localstack/localenv.py" in text
