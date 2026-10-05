"""Unit tests for scripts/check_digichat_image_binding.py (DIG-1242).

DIG-1242 found prod running ``digichat:v2.3.2`` with no machine-readable link
from the pushed image back to the commit that built it: the git tag
``digichat-v2.3.2`` did resolve to a commit, but the ACR image carried no OCI
annotation, and the ACR tag ladder carried hand-pushed debug tags
(``-error1..3``, ``-counter1..9``, ``-boot1``) that nothing could tie to a
build. So "which commit is running in prod" was answerable only by reading
someone's shell history.

This checker makes that link assertable offline: resolve ``digichat-vX.Y.Z`` to
a commit, read ``org.opencontainers.image.revision`` off an image, and require
the two to agree. It is pure -- it takes already-collected facts on stdin --
so every branch is testable without a registry, a daemon, or network.

The branches that matter are the ones that would otherwise be a silent pass:

* an image with **no** revision annotation must fail, not skip. Before
  DIG-1242 every released image looked exactly like this, so "no annotation"
  cannot mean "fine".
* a tag whose version does not match ``package.json`` must fail, because that
  is the drift the deleted publish workflow used to refuse.
* an unknown version must fail rather than pass through as "not my problem".
"""

from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from pathlib import Path
from typing import Any  # score:allow untyped any -- dynamically loaded module

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_digichat_image_binding.py"
_DOCKERFILE = REPO_ROOT / "apps" / "digichat" / "Dockerfile"

# The commit DIG-1242 verified as the target of the digichat-v2.3.2 tag.
V232_COMMIT = "14639ac0ca9947beeb62d6b1971ebd69e3554be1"
# A real released image digest from the ACR ledger (prod, 2026-09-21).
V232_DIGEST = "sha256:c5708729fea26c0689057beda8d83a0da9f4ad6c59752871bded2c108a9f1e39"

pytestmark = pytest.mark.unit


def _load_module() -> Any:
    spec = importlib.util.spec_from_file_location("check_digichat_image_binding", _SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def mod() -> Any:
    return _load_module()


def _facts(
    *,
    version: str = "2.3.2",
    package_version: str = "2.3.2",
    tag_commit: str | None = V232_COMMIT,
    image_revision: str | None = V232_COMMIT,
    image_digest: str = V232_DIGEST,
    image_ref: str = "datatapchatregistry.azurecr.io/digichat:v2.3.2",
    tag_ref: str = "digichat-v2.3.2",
) -> dict[str, Any]:
    return {
        "version": version,
        "package_version": package_version,
        "tag": tag_ref,
        "tag_commit": tag_commit,
        "image_ref": image_ref,
        "image_digest": image_digest,
        "image_revision": image_revision,
    }


# --- the happy path -------------------------------------------------------


def test_matching_binding_passes(mod: Any) -> None:
    result = mod.check(_facts())
    assert result.ok is True
    assert result.problems == []
    assert result.commit == V232_COMMIT


def test_short_and_full_commit_both_match(mod: Any) -> None:
    """A label carrying an abbreviated sha must still bind."""
    for short in (V232_COMMIT[:12], V232_COMMIT[:7]):
        assert mod.check(_facts(image_revision=short)).ok is True


def test_digest_is_carried_through(mod: Any) -> None:
    result = mod.check(_facts())
    assert result.digest == V232_DIGEST


# --- the failure branches -------------------------------------------------


def test_missing_revision_annotation_fails(mod: Any) -> None:
    """Every pre-DIG-1242 image looks like this; it must not read as fine."""
    result = mod.check(_facts(image_revision=None))
    assert result.ok is False
    assert any("org.opencontainers.image.revision" in p for p in result.problems)


def test_empty_revision_annotation_fails(mod: Any) -> None:
    """The Dockerfile default is "" -- an empty label is not a binding."""
    result = mod.check(_facts(image_revision=""))
    assert result.ok is False


def test_revision_mismatch_fails(mod: Any) -> None:
    other = "f" * 40
    result = mod.check(_facts(image_revision=other))
    assert result.ok is False
    assert any("does not match" in p for p in result.problems)


def test_missing_tag_commit_fails(mod: Any) -> None:
    result = mod.check(_facts(tag_commit=None))
    assert result.ok is False
    assert any("digichat-v2.3.2" in p for p in result.problems)


def test_version_package_mismatch_fails(mod: Any) -> None:
    """The drift the deleted publish workflow refused to publish."""
    result = mod.check(_facts(package_version="2.4.0"))
    assert result.ok is False
    assert any("package.json" in p for p in result.problems)


def test_tag_version_mismatch_fails(mod: Any) -> None:
    """A tag of digichat-v2.3.2 must not be checked against a 2.4.0 package."""
    result = mod.check(_facts(tag_ref="digichat-v2.4.0"))
    assert result.ok is False
    assert any("digichat-v2.4.0" in p for p in result.problems)


def test_malformed_revision_fails(mod: Any) -> None:
    result = mod.check(_facts(image_revision="not-a-sha"))
    assert result.ok is False


# --- the caller must read package.json from the tag's tree ---------------


def test_package_version_from_the_wrong_tree_is_reported_as_drift(
    mod: Any,
) -> None:
    """A live pitfall, verified 2026-10-06 against the real repo.

    ``package.json`` on ``develop`` read 2.4.0 while the ``digichat-v2.3.2``
    tree read 2.3.2, so auditing the running v2.3.2 image against the checkout
    reported "image version 2.3.2 does not match package.json version 2.4.0" --
    true of the checkout, false of the image. The fix belongs in the caller
    (``git show <tag>:apps/digichat/package.json``), so this test documents
    that the checker cannot do it for them: given the wrong tree it reports the
    mismatch loudly rather than quietly passing.
    """
    result = mod.check(_facts(version="2.3.2", package_version="2.4.0"))
    assert result.ok is False
    assert any("2.3.2" in p and "2.4.0" in p for p in result.problems)


def test_package_version_from_the_tag_tree_passes(mod: Any) -> None:
    result = mod.check(_facts(version="2.3.2", package_version="2.3.2"))
    assert result.ok is True


# --- CLI surface ----------------------------------------------------------


def _run(*args: str, stdin: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["python3", str(_SCRIPT), *args],
        input=stdin,
        capture_output=True,
        text=True,
        cwd=REPO_ROOT,
        check=False,
    )


def test_cli_exit_zero_on_match(mod: Any) -> None:
    proc = _run("--facts", "-", stdin=json.dumps(_facts()))
    assert proc.returncode == 0, proc.stderr
    assert "digichat-v2.3.2" in proc.stdout


def test_cli_exit_one_on_mismatch() -> None:
    proc = _run("--facts", "-", stdin=json.dumps(_facts(image_revision="f" * 40)))
    assert proc.returncode == 1
    assert "FAIL" in proc.stdout


def test_cli_json_output_shape() -> None:
    proc = _run("--facts", "-", "--json", stdin=json.dumps(_facts()))
    assert proc.returncode == 0, proc.stderr
    payload = json.loads(proc.stdout)
    assert payload["ok"] is True
    assert payload["commit"] == V232_COMMIT
    assert payload["problems"] == []


def test_cli_invalid_json_is_a_hard_error() -> None:
    proc = _run("--facts", "-", stdin="{not json")
    assert proc.returncode == 2


# --- the Dockerfile must keep the annotation hook -------------------------


def test_dockerfile_declares_the_revision_label() -> None:
    """If the label is removed the checker silently has nothing to read."""
    text = _DOCKERFILE.read_text()
    assert "org.opencontainers.image.revision" in text
    assert "ARG DIGICHAT_REVISION" in text


def test_dockerfile_does_not_bake_embed_tenants() -> None:
    """Regression guard: embed tokens must never enter layer history.

    The name may appear in a warning comment -- it does, deliberately -- so
    this asserts on the forms that would actually capture a value.
    """
    text = _DOCKERFILE.read_text()
    for forbidden in ("ARG DIGICHAT_EMBED_TENANTS", "ENV DIGICHAT_EMBED_TENANTS"):
        assert forbidden not in text
