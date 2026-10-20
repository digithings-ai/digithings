"""The local stack's own environment defaults (DIG-4661).

``config/contract/secrets.yaml`` renders a canonical selfhost value for every
secret. ``localenv`` then sets the local stack's own values over the rendered
ones, and those are what docker compose hands the containers (``env_file:
.env``). An override that is missing leaves a container aimed at a host
service it must never touch - here the digisearch monitor store, whose
contract DSN names 127.0.0.1:54329, Paperclip's own board database on this
host.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from scripts.localstack import localenv

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

#: Paperclip's own board database port on this host.
BOARD_DB_PORT = 54329


def _compose_service_block(service: str) -> list[str]:
    """The lines of one compose service, so a scan cannot pick another's."""
    lines = (REPO_ROOT / "docker-compose.yml").read_text(encoding="utf-8").splitlines()
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
    text = (REPO_ROOT / "config" / "contract" / "secrets.yaml").read_text(encoding="utf-8")
    start = text.index("DIGISEARCH_MONITORS_DB")
    match = re.search(r'template:\s*"([^"]+)"', text[start:])
    assert match, "the contract no longer renders a template for the monitors store"
    return match.group(1)


def test_the_local_store_path_is_the_one_the_compose_service_uses():
    """The path has to follow the service, or the store stops persisting."""
    block = _compose_service_block("digisearch")
    workspace = [line.strip() for line in block if line.strip().startswith("- DIGI_WORKSPACE=")]
    assert len(workspace) == 1, f"expected one DIGI_WORKSPACE line, got {workspace}"
    store = (REPO_ROOT / "digisearch" / "src" / "digisearch" / "monitors" / "store.py").read_text(
        encoding="utf-8"
    )
    directory = re.search(r'_WORKSPACE_DB_DIR\s*=\s*"([^"]+)"', store)
    filename = re.search(r'_DB_FILENAME\s*=\s*"([^"]+)"', store)
    assert directory and filename, "the monitor store constants moved: the scan is void"
    root = workspace[0].split("=", 1)[1].strip()
    expected = f"{root}/{directory.group(1)}/{filename.group(1)}"
    assert localenv.LOCAL_DIGISEARCH_MONITORS_DB == expected


def test_the_rendered_env_does_not_aim_the_monitors_store_at_the_board_database(
    tmp_path,
):
    """The repro: the rendered .env carried 127.0.0.1:54329."""
    (tmp_path / ".dev.vars").write_text(
        f"DIGISEARCH_MONITORS_DB={_contract_monitors_template()}\n", encoding="utf-8"
    )
    localenv.write_env(tmp_path, env={})
    rendered = localenv.read_env_file(tmp_path / ".env")
    value = rendered["DIGISEARCH_MONITORS_DB"]
    assert str(BOARD_DB_PORT) not in value
    assert value == localenv.LOCAL_DIGISEARCH_MONITORS_DB


def test_the_local_override_wins_over_the_contract_value():
    overrides = localenv.local_overrides({}, {})
    assert overrides["DIGISEARCH_MONITORS_DB"] == localenv.LOCAL_DIGISEARCH_MONITORS_DB
