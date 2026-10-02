"""Pin the stack container's seed configuration against drift.

Two classes of bug live here, both of which produce a silently degraded OCC
corpus rather than an error:

1. ``SEED_VER`` is written as a literal in both ``seed_chroma.sh`` (which
   creates the marker) and ``start_digisearch.sh`` (which waits for it). The
   seeder deletes the previous version's marker on every boot, so if only one
   file is bumped the wait can never observe success: each boot burns the full
   180 s readiness window, and a genuine seed failure degrades to the generic
   timeout WARN instead of the loud ``SEED_FAILED`` one.

2. ``DIGISEARCH_EMBEDDING_PROVIDER`` is global to digisearch, not per-index.
   The write path pins it in ``scripts/index_occ_tickets.py``; the read path
   falls back to the minilm preset when it is unset. Chroma then raises
   ``EmbeddingModelMismatchError``, which is outside ``_BACKEND_ERRORS`` and so
   escapes the fan-out comprehension, taking ``occ_help`` down alongside a
   broken ``occ_tickets``.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
RELEASE = REPO_ROOT / "infra" / "digichat-release"

SEED_VERSION_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"


def _shell_var(path: Path, name: str) -> str:
    match = re.search(rf'^{name}="([^"]*)"', path.read_text(encoding="utf-8"), re.MULTILINE)
    assert match is not None, f"{name} not found in {path}"
    return match.group(1)


def _compose_stack_environment() -> dict[str, str]:
    compose = yaml.safe_load(
        (RELEASE / "compose.profile-a-bundle.override.yml").read_text(encoding="utf-8")
    )
    return compose["services"]["digithings-stack"]["environment"]


def _wrangler_vars() -> dict[str, str]:
    import tomllib

    return tomllib.loads((CONTAINER / "wrangler.toml").read_text(encoding="utf-8"))["vars"]


def test_seed_version_matches_between_seeder_and_waiter() -> None:
    """The waiter's marker path must equal the seeder's."""
    seeder = _shell_var(CONTAINER / "container" / "seed_chroma.sh", "SEED_VER")
    waiter = _shell_var(CONTAINER / "container" / "start_digisearch.sh", "SEED_VER")
    assert seeder == waiter, (
        f"SEED_VER drift: seed_chroma.sh writes {seeder!r} but start_digisearch.sh waits for "
        f"{waiter!r}. seed_chroma.sh deletes the previous marker on boot, so the waiter would "
        "never see success and every boot would time out."
    )


def test_seed_version_clears_every_prior_marker() -> None:
    """The seeder must delete the marker it used to write, or a stale volume
    reports 'already done' before the new seed content exists."""
    current = _shell_var(CONTAINER / "container" / "seed_chroma.sh", "SEED_VER")
    script = (CONTAINER / "container" / "seed_chroma.sh").read_text(encoding="utf-8")
    for prior in ("v1", "v2", "v3", "v4"):
        if prior == current:
            continue
        assert f".stack_chroma_seeded_{prior}" in script, (
            f"seed_chroma.sh no longer clears the {prior} marker while SEED_VER is {current}"
        )


@pytest.mark.parametrize("layer", ["compose", "wrangler"])
def test_embedding_provider_pinned_on_every_runtime_layer(layer: str) -> None:
    """Each layer that runs digisearch must pin the provider its seed writes with."""
    if layer == "compose":
        env = _compose_stack_environment()
        value = env.get("DIGISEARCH_EMBEDDING_PROVIDER")
        scope = "compose.profile-a-bundle.override.yml digithings-stack.environment"
    else:
        env = _wrangler_vars()
        value = env.get("DIGISEARCH_EMBEDDING_PROVIDER")
        scope = "wrangler.toml [vars]"

    assert value == SEED_VERSION_MODEL_ID, (
        f"{scope} sets DIGISEARCH_EMBEDDING_PROVIDER={value!r}, but the occ_tickets write path "
        f"pins {SEED_VERSION_MODEL_ID!r}. Reading an index under a different embedder raises "
        "EmbeddingModelMismatchError, which is not in _BACKEND_ERRORS and aborts the whole "
        "occ_help,occ_tickets fan-out."
    )


def test_env_example_documents_the_same_provider() -> None:
    """The operator-facing example must not teach an unpinned provider."""
    text = (RELEASE / ".env.profile-a-bundle.example").read_text(encoding="utf-8")
    match = re.search(r"^DIGISEARCH_EMBEDDING_PROVIDER=(.+)$", text, re.MULTILINE)
    assert match is not None, ".env.profile-a-bundle.example does not document the provider pin"
    assert match.group(1).strip() == SEED_VERSION_MODEL_ID
