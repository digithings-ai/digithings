"""scripts/run_local.sh used to 503 a normal JWT.

The launcher turns JWT verification on and does not start Redis. With the
fail-closed blocklist default, an unset URL rejects every jti. make stack-local
opts out; compose forwards a Redis URL. This script has to do one of those.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
RUN_LOCAL = REPO_ROOT / "scripts" / "run_local.sh"
BLOCKLIST = REPO_ROOT / "digikey" / "src" / "digikey" / "blocklist.py"


def _decision_source() -> str:
    text = RUN_LOCAL.read_text()
    start = text.index("export DIGIKEY_JWKS_URL=")
    end = text.index('# Avoid "address already in use"')
    return text[start:end]


def _digikey_env(**extra: str) -> list[str]:
    script = _decision_source() + 'printf "%s\\n" "${digikey_env[@]}"\n'
    env = {"PATH": "/usr/bin:/bin", **extra}
    proc = subprocess.run(
        ["bash", "-c", script],
        check=True,
        capture_output=True,
        text=True,
        env=env,
    )
    return proc.stdout.splitlines()


def test_code_default_stays_fail_closed() -> None:
    """The local opt-out lives in the launcher, not in blocklist.py."""
    assert 'os.environ.get("DIGIKEY_REQUIRE_BLOCKLIST", "1")' in BLOCKLIST.read_text()


def test_clean_local_run_opts_out() -> None:
    """No Redis URL used to leave the requirement unset, and middleware 503'd."""
    rows = _digikey_env()
    assert "DIGIKEY_REQUIRE_BLOCKLIST=0" in rows
    assert not any(row.startswith("DIGIKEY_BLOCKLIST_REDIS_URL=") for row in rows)


def test_redis_url_is_forwarded_and_stays_fail_closed() -> None:
    url = "redis://127.0.0.1:6379/0"
    rows = _digikey_env(DIGIKEY_BLOCKLIST_REDIS_URL=url)
    assert f"DIGIKEY_BLOCKLIST_REDIS_URL={url}" in rows
    assert not any(row.startswith("DIGIKEY_REQUIRE_BLOCKLIST=") for row in rows)


def test_explicit_requirement_is_kept() -> None:
    rows = _digikey_env(DIGIKEY_REQUIRE_BLOCKLIST="1")
    assert "DIGIKEY_REQUIRE_BLOCKLIST=1" in rows


def test_both_servers_receive_the_digikey_env() -> None:
    text = RUN_LOCAL.read_text()
    launches = [line for line in text.splitlines() if "server:app" in line]
    assert launches == [
        '  $UVICORN digiquant.server:app --host 127.0.0.1 --port "$DQ_PORT" &',
        '  $UVICORN digigraph.server:app --host 127.0.0.1 --port "$DG_PORT" &',
    ]
    assert text.count('"${digikey_env[@]}"') == 2
