"""searxng sidecar must probe with wget and pin the commit production builds (#3853/#3859/#3239).

Probed 2026-09-11 against searxng/searxng:latest: curl MISSING, wget and
python3 present at /usr/sbin — so a curl healthcheck fails forever and the
container never becomes healthy.

Upstream tags are `latest` or `YYYY.M.D-<hash>`; a bare `YYYY.M.D` tag does
not exist, so `compose pull` fails on it. Since #3239 compose no longer floats:
it pins the release tag for the same searxng commit
`Dockerfile.digithings-stack-cloudflare` builds from, and this test derives that
expected tag from the Dockerfile instead of restating it, so a bump of
SEARXNG_COMMIT cannot leave compose on a stale engine. The image digest is still
unpinned by decision (digisearch/ARCHITECTURE.md, #3871); that is not asserted
here.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "docker-compose.yml"
PROD_DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
TAG_RE = re.compile(r"\d{4}\.\d{1,2}\.\d{1,2}-[0-9a-f]+")
COMMIT_RE = re.compile(r"^ARG SEARXNG_COMMIT=([0-9a-f]{40})", re.MULTILINE)
VERSION_RE = re.compile(r'VERSION_STRING = "([^"]+)"')
DOCKER_TAG_RE = re.compile(r'DOCKER_TAG = "([^"]+)"')


def _searxng_service() -> dict:
    doc = yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))
    return doc["services"]["searxng"]


def _prod_searxng_tag() -> str:
    """The upstream release tag for the searxng commit the production bundle builds.

    Taken from the Dockerfile's own DOCKER_TAG literal, which is the in-repo statement of
    that mapping, and cross-checked against SEARXNG_COMMIT and VERSION_STRING. It is not
    recomputed from the commit here: upstream's tag suffix is a 9-character hex prefix, so
    a width constant in this file would be a guess, and a wrong guess fails as a false
    parity error rather than as a bad constant.
    """
    text = PROD_DOCKERFILE.read_text(encoding="utf-8")
    commit, version, tag = (
        pattern.search(text) for pattern in (COMMIT_RE, VERSION_RE, DOCKER_TAG_RE)
    )
    assert commit and version and tag, (
        f"cannot derive the production searxng tag from {PROD_DOCKERFILE.name}: "
        f"SEARXNG_COMMIT={'found' if commit else 'MISSING'}, "
        f"VERSION_STRING={'found' if version else 'MISSING'}, "
        f"DOCKER_TAG={'found' if tag else 'MISSING'}"
    )
    version_string, _, suffix = tag.group(1).rpartition("-")
    assert version_string == version.group(1), (
        f"DOCKER_TAG {tag.group(1)!r} does not carry VERSION_STRING {version.group(1)!r}"
    )
    assert commit.group(1).startswith(suffix), (
        f"DOCKER_TAG hash {suffix!r} is not a prefix of SEARXNG_COMMIT {commit.group(1)!r}"
    )
    return tag.group(1)


def test_searxng_healthcheck_uses_wget_not_curl() -> None:
    test = _searxng_service()["healthcheck"]["test"]
    flat = " ".join(str(part) for part in test)
    assert "curl" not in flat, f"searxng image has no curl; healthcheck {test} can never pass"
    assert "wget" in flat, f"searxng healthcheck must probe with wget, got {test}"


def test_searxng_image_tag_is_the_commit_the_prod_bundle_builds() -> None:
    expected = _prod_searxng_tag()
    image = str(_searxng_service()["image"])
    repository, _, tag = image.partition(":")
    assert repository == "searxng/searxng", f"unexpected searxng repository in {image!r}"
    assert tag != "latest", (
        "searxng floats again: `:latest` is not reproducible and can drift from the "
        f"production bundle. Pin the commit production builds: searxng/searxng:{expected}"
    )
    assert tag == expected, (
        f"compose runs searxng {tag!r} but the production bundle builds the commit tagged "
        f"{expected!r} (SEARXNG_COMMIT / VERSION_STRING in {PROD_DOCKERFILE.name}). Local "
        "search results then differ from production."
    )


def test_searxng_image_tag_is_an_upstream_tag_shape() -> None:
    tag = str(_searxng_service()["image"]).partition(":")[2]
    assert TAG_RE.fullmatch(tag), (
        f"searxng image tag {tag!r} matches no upstream tag (upstream ships `latest` or "
        "`YYYY.M.D-<hash>` only; a bare `YYYY.M.D` does not exist and `compose pull` fails)"
    )
