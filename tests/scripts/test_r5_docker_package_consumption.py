"""R5 images install packages. They do not COPY sibling module trees.

DIG-3701. The packaged inputs are produced by
``scripts/package_r5_image_inputs.py`` and are gitignored. This test pins
the Dockerfile contract those inputs have to satisfy.
"""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
RUNNER = "Dockerfile.digiquant-runner"
STACK = "Dockerfile.digithings-stack-cloudflare"
DIGICHAT = (
    "Dockerfile.digichat-cloudflare",
    "apps/digichat/Dockerfile",
)
SIBLING_COPY = (
    "COPY digibase",
    "COPY digikey",
    "COPY digifetch",
    "COPY digiquant ",
    "COPY digiquant/",
    "COPY digigraph",
    "COPY digillm",
    "COPY digitrace",
    "COPY digiclaw",
    "COPY digisearch",
    "COPY digivault",
    "COPY packages/design",
    "COPY packages/ui",
    "COPY packages/digichat-ui",
    "COPY apps/dashboard",
    "COPY apps/digiquant-runner",
    "COPY scripts/refresh_market_data_r2.py",
)
FORBIDDEN_REGISTRIES = ("ghcr.io", "azurecr.io", "forbiddenexample_registry")


def _text(rel: str) -> str:
    return (REPO / rel).read_text(encoding="utf-8")


@pytest.mark.parametrize("rel", (RUNNER, STACK, *DIGICHAT))
def test_images_do_not_copy_sibling_modules(rel: str) -> None:
    text = _text(rel)
    for needle in SIBLING_COPY:
        assert needle not in text, f"{rel} still copies sibling path {needle}"
    for registry in FORBIDDEN_REGISTRIES:
        assert registry not in text, f"{rel} names {registry}"
    # Exact ARG line. A host substring check is the CodeQL incomplete-URL pattern.
    default_push = "ARG IMAGE_PUSH_REGISTRY=registry.cloudflare.com"
    assert any(line.strip() == default_push for line in text.splitlines())


def test_dockerignore_keeps_runner_payload() -> None:
    """Basename rules ignore every `scripts` and `.github` dir. The payload
    copies have to be re-included or docker build drops them."""
    text = _text(".dockerignore")
    for needle in (
        "!image-packages/runner/payload/scripts",
        "!image-packages/runner/payload/.github",
        "!image-packages/runner/payload/digiquant/scripts",
    ):
        assert needle in text


def test_runner_keeps_frozen_sync_and_payload_layout() -> None:
    text = _text(RUNNER)
    assert "uv sync --frozen --no-install-project --no-dev" in text
    assert "image-packages/runner/project/uv.lock" in text
    assert "image-packages/runner/payload/opt/runner/" in text
    assert "DIGI_CONFIG_PATH=/app/config" in text


def test_stack_installs_nine_modules_and_keeps_bakes() -> None:
    text = _text(STACK)
    assert "image-packages/stack/requirements.txt" in text
    for package in (
        "digibase==0.1.0",
        "digikey==0.1.0",
        "digitrace[tracing]==0.1.0",
        "digillm==0.1.0",
        "digigraph[mcp]==0.1.0",
        "digifetch==0.1.0",
        "digiclaw==0.1.0",
        "digivault[service]==0.1.0",
    ):
        assert package in text
    line = next(
        line for line in text.splitlines() if "digisearch[" in line and "uv pip install" in line
    )
    assert "web-search" in line
    assert "embedding-multilingual" in line
    assert "SEARXNG_COMMIT=a1144dda3e97668c9d445022b7019c224cd4bb1e" in text
    assert "litellm[proxy]==1.83.14" in text
    assert "snapshot_download" in text


@pytest.mark.parametrize("rel", DIGICHAT)
def test_digichat_consumes_packaged_npm_and_root_lock(rel: str) -> None:
    text = _text(rel)
    assert "COPY package.json package-lock.json ./" in text
    assert "COPY tsconfig.base.json ./tsconfig.base.json" in text
    assert "COPY config/byok-providers.json" in text
    assert "COPY apps/digichat ./apps/digichat" in text
    assert "image-packages/digichat/npm/" in text
    assert "digithings-design-" in text
    assert "digithings-ui-" in text
    assert "digithings-digichat-ui-" in text
