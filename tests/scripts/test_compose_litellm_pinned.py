"""The LiteLLM proxy ships as the digithings `digillm` image, pinned (DIG-1780, #5337).

Red line ratified on DIG-1768/DIG-1780: LiteLLM comes from the pinned PyPI wheel
only, never the vendor (berriai) Docker image. So:

* every compose file runs a `digillm` service from ghcr.io/digithings-ai/digillm at
  an exact version tag (never a floating tag), with the `litellm` network alias
  and port 4000 so existing OPENAI_API_BASE callers keep working;
* Dockerfile.digillm and the Cloudflare stack Dockerfile install the SAME exact
  litellm[proxy] version (hosted and local must not drift);
* no tracked compose file, Dockerfile, contract or workflow names berriai.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "infra" / "digichat-release" / "compose.profile-a.yml",
)
DIGILLM_DOCKERFILE = REPO_ROOT / "Dockerfile.digillm"
STACK_DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
PINNED = re.compile(r"^ghcr\.io/digithings-ai/digillm:\d+\.\d+\.\d+(@sha256:[0-9a-f]{64})?$")
EXACT = re.compile(r"^\d+\.\d+\.\d+$")


def _service(path: Path) -> dict:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    services = doc["services"]
    assert "litellm" not in services, f"{path}: raw litellm service is back; use digillm"
    return services["digillm"]


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.name)
def test_digillm_image_pinned(compose_path: Path) -> None:
    image = _service(compose_path)["image"]
    assert PINNED.match(image), f"{compose_path}: digillm image not pinned to an exact version: {image}"


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.name)
def test_digillm_keeps_litellm_alias_and_port(compose_path: Path) -> None:
    svc = _service(compose_path)
    assert svc.get("container_name") == "digi-digillm"
    assert "litellm" in svc["networks"]["default"]["aliases"]
    assert any(str(p).endswith(":4000:4000") for p in svc["ports"])


def test_digillm_pin_consistent() -> None:
    assert len({_service(p)["image"] for p in COMPOSE_FILES}) == 1


def _digillm_litellm_version() -> str:
    m = re.search(r"^ARG LITELLM_VERSION=(\S+)$", DIGILLM_DOCKERFILE.read_text(), re.M)
    assert m, "Dockerfile.digillm must declare ARG LITELLM_VERSION=<exact>"
    return m.group(1)


def test_litellm_version_exact_and_same_everywhere() -> None:
    version = _digillm_litellm_version()
    assert EXACT.match(version), f"litellm version must be exact X.Y.Z, got {version}"
    stack = re.findall(r"litellm\[proxy\]==([\w.]+)", STACK_DOCKERFILE.read_text())
    assert stack == [version], (
        f"Cloudflare stack installs litellm {stack}, digillm image installs {version}"
    )


def test_digillm_base_image_pinned_by_digest() -> None:
    m = re.search(r"^FROM (\S+)", DIGILLM_DOCKERFILE.read_text(), re.M)
    assert m and re.search(r"@sha256:[0-9a-f]{64}$", m.group(1)), m


def test_no_berriai_image_anywhere() -> None:
    tracked = subprocess.run(
        ["git", "grep", "-l", "-i", "berriai/litellm", "--",
         "*.yml", "*.yaml", "Dockerfile*", "*/Dockerfile*", "*.toml", "config/contract/*"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    ).stdout.split()
    assert tracked == [], f"vendor LiteLLM image referenced in: {tracked}"
