"""Stack boot derives DIGIKEY_PUBLIC_KEY_PEM so digigraph can verify licenses."""

from __future__ import annotations

from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER = REPO_ROOT / "apps" / "digithings-stack-cloudflare" / "container"
DOCKERFILE = REPO_ROOT / "infra" / "docker" / "Dockerfile.digithings-stack-cloudflare"


def test_entrypoint_derives_public_key_only_from_a_valid_key_and_never_overrides() -> None:
    text = (CONTAINER / "entrypoint.sh").read_text()
    assert 'if [ "$pem_ok" -eq 1 ] && [ -z "${DIGIKEY_PUBLIC_KEY_PEM:-}" ]; then' in text
    assert "python3 /license_public_key.py 2>/dev/null || true" in text
    # Derivation runs after the private key is validated.
    assert text.index("pem_ok=1") < text.index("/license_public_key.py")


def test_image_ships_the_helper() -> None:
    assert (
        "COPY apps/digithings-stack-cloudflare/container/license_public_key.py "
        "/license_public_key.py" in DOCKERFILE.read_text()
    )
