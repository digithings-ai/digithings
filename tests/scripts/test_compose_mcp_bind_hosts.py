"""The MCP servers compose publishes must bind every interface in the container.

compose publishes ``digisearch-mcp`` as ``127.0.0.1:8765 -> 8765`` and
``digivault-mcp`` as ``127.0.0.1:8769 -> 8769``, but both servers listen on
their own loopback by default (``digisearch/src/digisearch/mcp_server.py`` and
``digivault/src/digivault/mcp_server.py`` read ``DIGISEARCH_MCP_HOST`` and
``DIGIVAULT_MCP_HOST``). A process listening on the container's loopback is
unreachable through a published port: the host curl answers nothing at all and
the other containers cannot reach it by service name - and the OCC embed
config uses ``http://digisearch-mcp:8765/mcp``.

So the bind host is set in the compose file, with the same shape as the
services that already do it there (``digiquant-mcp`` and the other MCP
profiles): the container binds every interface, the published port stays on
the host loopback. The default is 0.0.0.0, and an operator who wants another bind
writes the variable in the root ``.env`` - compose interpolates it from there
and it wins over the default (DIG-4797).
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
CONTRACT = REPO_ROOT / "config" / "contract" / "contract.yaml"

#: service -> the variable that holds its bind host.
BIND_HOSTS = {
    "digisearch-mcp": "DIGISEARCH_MCP_HOST",
    "digivault-mcp": "DIGIVAULT_MCP_HOST",
}


def _service(name: str) -> dict:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return doc["services"][name]


def _environment(service: dict) -> list[str]:
    environment = service.get("environment") or []
    if isinstance(environment, dict):
        return [f"{key}={value}" for key, value in environment.items()]
    return [str(item) for item in environment]


@pytest.mark.parametrize("service, variable", sorted(BIND_HOSTS.items()))
def test_the_mcp_server_binds_every_interface_in_its_container(
    service: str, variable: str
) -> None:
    """The bind host is set, and it is set with a default of 0.0.0.0.

    The value is interpolated (``${VAR:-0.0.0.0}``) rather than pinned, so
    the operator's root ``.env`` still wins; a literal 0.0.0.0 in the file
    would make that impossible.
    """
    values = _environment(_service(service))
    assert f"{variable}=${{{variable}:-0.0.0.0}}" in values, values


@pytest.mark.parametrize("service, variable", sorted(BIND_HOSTS.items()))
def test_the_mcp_server_reads_the_root_env(service: str, variable: str) -> None:
    """The operator's value has to reach compose, so the service reads .env."""
    env_file = _service(service).get("env_file") or []
    if isinstance(env_file, dict):
        env_file = list(env_file.values())
    assert ".env" in [str(item) for item in env_file], env_file


@pytest.mark.parametrize("service", sorted(BIND_HOSTS))
def test_the_published_mcp_port_stays_on_the_host_loopback(service: str) -> None:
    """The bind is inside the container; the host side stays on loopback.

    Every published port is checked, not the ones that already look right: a
    second entry publishing the same port on 0.0.0.0 would reach the network
    the host sits on, and a test that only looked for the loopback line would
    not see it.
    """
    ports = [str(port) for port in (_service(service).get("ports") or [])]
    assert ports, f"{service} publishes no port"
    for port in ports:
        assert port.startswith("127.0.0.1:"), f"{service} publishes {port} off loopback"


def test_the_contract_does_not_render_the_mcp_bind_hosts() -> None:
    """A rendered bind host would silently re-break the published port.

    compose prefers the interpolated value over the default, and the
    interpolated value comes from the root ``.env`` - which the contract
    renders. A contract key that rendered 127.0.0.1 would therefore win over
    the 0.0.0.0 default in the compose file and put the published port back
    to sleep, with nothing failing. The contract renders neither name today;
    this test says so out loud.
    """
    rendered = CONTRACT.read_text(encoding="utf-8")
    for variable in BIND_HOSTS.values():
        assert variable not in rendered, (
            f"the contract renders {variable}: compose would interpolate that "
            "over the 0.0.0.0 default and the published port would answer "
            "nothing again"
        )
