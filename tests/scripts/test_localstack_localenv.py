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


# ------------------------------------------------ the operator's own values

#: The values SELF_HOST.md 7.1 tells the operator to set in the root .env.
OPERATOR_KEYS = (
    "LITELLM_MASTER_KEY",
    "LITELLM_PROXY_API_KEY",
    "OLLAMA_API_KEY",
    "DIGIKEY_LITELLM_PROXY_KEY",
    "DIGI_MODEL_MODES_FILE",
    "DIGI_CONFIG_PATH",
)


def test_an_operator_value_survives_the_render(tmp_path):
    """The repro: `dt up` rebuilt the root .env and dropped the operator's value."""
    (tmp_path / ".env").write_text("LITELLM_MASTER_KEY=operator-value\n", encoding="utf-8")
    (tmp_path / ".dev.vars").write_text("CORE_SUPABASE_SERVICE_KEY=fresh\n", encoding="utf-8")
    localenv.write_env(tmp_path, env={})
    rendered = localenv.read_env_file(tmp_path / ".env")
    assert rendered["LITELLM_MASTER_KEY"] == "operator-value"
    assert rendered["CORE_SUPABASE_SERVICE_KEY"] == "fresh"


@pytest.mark.parametrize("name", OPERATOR_KEYS)
def test_every_documented_operator_value_survives_the_render(tmp_path, name):
    """Each value SELF_HOST.md 7.1 documents is the operator's and is kept."""
    (tmp_path / ".env").write_text(f"{name}=operator-value\n", encoding="utf-8")
    localenv.write_env(tmp_path, env={})
    assert localenv.read_env_file(tmp_path / ".env")[name] == "operator-value"


def test_a_rendered_value_still_wins_over_the_copy_in_the_root_env(tmp_path):
    """The render owns the values it produces, so a stale copy does not win."""
    (tmp_path / ".dev.vars").write_text("CORE_SUPABASE_SERVICE_KEY=fresh\n", encoding="utf-8")
    (tmp_path / ".env").write_text("CORE_SUPABASE_SERVICE_KEY=stale\n", encoding="utf-8")
    localenv.write_env(tmp_path, env={})
    assert localenv.read_env_file(tmp_path / ".env")["CORE_SUPABASE_SERVICE_KEY"] == "fresh"


def test_the_local_override_still_wins_over_the_root_env(tmp_path):
    """The local values win over everything, the operator's copy included."""
    (tmp_path / ".env").write_text("SUPABASE_URL=http://127.0.0.1:1\n", encoding="utf-8")
    localenv.write_env(tmp_path, env={})
    rendered = localenv.read_env_file(tmp_path / ".env")
    assert rendered["SUPABASE_URL"] == f"http://127.0.0.1:{localenv.api_port({})}"
