"""searxng sidecar must probe with wget and pin a resolvable image tag (#3853/#3859).

Probed 2026-09-11 against searxng/searxng:latest: curl MISSING, wget and
python3 present at /usr/sbin — so a curl healthcheck fails forever and the
container never becomes healthy. Upstream tags are `latest` or
`YYYY.M.D-<hash>` (a bare `YYYY.M.D` tag does not exist, `compose pull`
fails), per the DockerHub tag listing and the official docs (which use
`:latest`).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
TAG_RE = re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}-[0-9a-f]+")


def _searxng_service() -> dict:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return doc["services"]["searxng"]


def test_searxng_healthcheck_uses_wget_not_curl() -> None:
    test = _searxng_service()["healthcheck"]["test"]
    flat = " ".join(str(part) for part in test)
    assert "curl" not in flat, f"searxng image has no curl; healthcheck {test} can never pass"
    assert "wget" in flat, f"searxng healthcheck must probe with wget, got {test}"


def test_searxng_image_tag_resolves_upstream() -> None:
    image = _searxng_service()["image"]
    _, _, tag = str(image).partition(":")
    assert tag == "latest" or TAG_RE.fullmatch(tag), (
        f"searxng image tag {tag!r} matches no upstream tag "
        "(upstream ships `latest` or `YYYY.M.D-<hash>` only)"
    )
