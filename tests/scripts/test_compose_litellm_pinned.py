"""LiteLLM image must be pinned by exact tag and digest (#5337).

The floating ``main-stable`` tag moved upstream and broke the e2e compose stack
(digi-litellm exited 3) with no change on our side. Bump the pin on purpose.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILES = (
    REPO_ROOT / "docker-compose.yml",
    REPO_ROOT / "infra" / "digichat-release" / "compose.profile-a.yml",
)
PINNED = re.compile(r"^[\w./-]+/berriai/litellm:v\d+\.\d+\.\d+[\w.-]*@sha256:[0-9a-f]{64}$")


def _image(path: Path) -> str:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    return doc["services"]["litellm"]["image"]


@pytest.mark.parametrize("compose_path", COMPOSE_FILES, ids=lambda p: p.name)
def test_litellm_image_pinned(compose_path: Path) -> None:
    image = _image(compose_path)
    assert PINNED.match(image), f"{compose_path}: litellm image not pinned by tag+digest: {image}"


def test_litellm_pin_consistent() -> None:
    assert len({_image(p) for p in COMPOSE_FILES}) == 1
