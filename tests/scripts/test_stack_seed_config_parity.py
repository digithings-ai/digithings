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

3. **Nothing on the boot path may invoke the ticket writer** (DIG-1438). A
   ``[program:seed_occ_tickets]`` block on ``develop`` re-ran
   ``scripts/index_occ_tickets`` at every container start, refilling
   ``occ_tickets`` with live Zammad ticket bodies and sender/subject metadata,
   unmasked. ``ZAMMAD_API_TOKEN`` is present in the live Worker env, so the
   credential the step needs is always there. The failure mode is invisible:
   the purge in DIG-1385 verifies zero rows and then the next boot refills
   them. Pinned by :func:`test_boot_chain_never_invokes_index_occ_tickets`.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
CONTAINER = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
RELEASE = REPO_ROOT / "infra" / "digichat-release"
DOCKERFILE = REPO_ROOT / "Dockerfile.digithings-stack-cloudflare"
SUPERVISORD = CONTAINER / "container" / "supervisor" / "supervisord.conf"
CONTAINER_SCRIPTS = CONTAINER / "container"

SEED_VERSION_MODEL_ID = "Xenova/paraphrase-multilingual-MiniLM-L12-v2"

#: The token the ticket writer needs. Present in the live Worker env, so the
#: boot step's own ``ZAMMAD_API_TOKEN`` gate is not a defence.
ZAMMAD_TOKEN_ENV = "ZAMMAD_API_TOKEN"


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


def _legacy_marker_clearing_merged() -> bool:
    """True once ``#4987`` (``86cb1ec5d``) is on this branch.

    That PR moved the seed marker to a provider-qualified ``${SEED_TAG}``, which
    replaces the per-version ``rm -f`` list (the tag always differs, so the seed
    always re-runs), and pinned ``DIGISEARCH_EMBEDDING_PROVIDER`` in the compose
    override and the example env. It landed on ``main`` only; ``develop`` does
    not have it yet, so the three tests that describe the post-``#4987`` state
    cannot hold here. Keyed on the marker change because that is the one this
    branch's own ``seed_chroma.sh`` is missing, and it flips by itself when the
    PR merges — no edit to this file needed at that point.
    """
    seeder = (CONTAINER_SCRIPTS / "seed_chroma.sh").read_text(encoding="utf-8")
    return ".stack_chroma_seeded_v1" in seeder


needs_4987 = pytest.mark.skipif(
    not _legacy_marker_clearing_merged(),
    reason=(
        "#4987 (86cb1ec5d) is on main but not on develop: the provider-qualified "
        "SEED_TAG marker and the DIGISEARCH_EMBEDDING_PROVIDER pins are absent here."
    ),
)


def test_seed_version_matches_between_seeder_and_waiter() -> None:
    """The waiter's marker path must equal the seeder's."""
    seeder = _shell_var(CONTAINER_SCRIPTS / "seed_chroma.sh", "SEED_VER")
    waiter = _shell_var(CONTAINER_SCRIPTS / "start_digisearch.sh", "SEED_VER")
    assert seeder == waiter, (
        f"SEED_VER drift: seed_chroma.sh writes {seeder!r} but start_digisearch.sh waits for "
        f"{waiter!r}. seed_chroma.sh deletes the previous marker on boot, so the waiter would "
        "never see success and every boot would time out."
    )


@needs_4987
def test_seed_version_clears_every_prior_marker() -> None:
    """The seeder must delete the marker it used to write, or a stale volume
    reports 'already done' before the new seed content exists.

    Only meaningful while the marker is the bare ``${SEED_VER}``. Under the
    provider-qualified ``${SEED_TAG}`` (#4987) the tag can never match a
    previous boot's name, so the ``rm -f`` list is unnecessary by construction.
    """
    current = _shell_var(CONTAINER_SCRIPTS / "seed_chroma.sh", "SEED_VER")
    script = (CONTAINER_SCRIPTS / "seed_chroma.sh").read_text(encoding="utf-8")
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
        if not _legacy_marker_clearing_merged():
            pytest.skip(
                "#4987 (86cb1ec5d) is on main but not on develop: "
                "compose.profile-a-bundle.override.yml does not pin the provider yet."
            )
        env = _compose_stack_environment()
        value = env.get("DIGISEARCH_EMBEDDING_PROVIDER")
        scope = "compose.profile-a-bundle.override.yml digithings-stack.environment"
    else:
        env = _wrangler_vars()
        value = env.get("DIGISEARCH_EMBEDDING_PROVIDER")
        scope = "wrangler.toml [vars]"

    assert value == SEED_VERSION_MODEL_ID, (
        f"{scope} sets DIGISEARCH_EMBEDDING_PROVIDER={value!r}, but the ticket write path "
        f"pins {SEED_VERSION_MODEL_ID!r}. Reading an index under a different embedder raises "
        "EmbeddingModelMismatchError, which is not in _BACKEND_ERRORS and aborts the whole "
        "corpus fan-out for that tenant."
    )


@needs_4987
def test_env_example_documents_the_same_provider() -> None:
    """The operator-facing example must not teach an unpinned provider."""
    text = (RELEASE / ".env.profile-a-bundle.example").read_text(encoding="utf-8")
    match = re.search(r"^DIGISEARCH_EMBEDDING_PROVIDER=(.+)$", text, re.MULTILINE)
    assert match is not None, ".env.profile-a-bundle.example does not document the provider pin"
    assert match.group(1).strip() == SEED_VERSION_MODEL_ID


# ── DIG-1438: the boot path must never invoke the ticket writer ───────────────
#
# ``[program:seed_occ_tickets]`` existed on ``develop`` only. It ran
# ``python -m scripts.index_occ_tickets --index occ_tickets`` at every container
# start, gated only on ``ZAMMAD_API_TOKEN`` being set — which it always is in the
# live Worker env. ``scripts/index_occ_tickets.py`` documents its chunk body as
# "full metadata, no masking", so each boot refilled ``occ_tickets`` with live
# customer ticket bodies plus sender/from/subject and the ``internal`` flag.
# It also made DIG-1385's purge reversible: that issue deletes the collection and
# confirms zero rows, and the next develop-built boot puts the rows back.
#
# The checks below are deliberately written against the *files that make up the
# boot chain* rather than against the one program block, so a rename or a move
# cannot quietly reintroduce the step.


def _boot_chain_files() -> list[Path]:
    """Every file supervisord, the entrypoint or the image build can run.

    ``container/`` holds the supervisor config, ``entrypoint.sh`` and the
    ``start_*`` / ``seed_*`` oneshots; the repo-root Dockerfile is what puts
    them into the image, so a COPY that ships a new seeder counts too.
    """
    files = sorted(p for p in CONTAINER_SCRIPTS.rglob("*") if p.is_file())
    files.append(DOCKERFILE)
    return files


def test_boot_chain_never_invokes_index_occ_tickets() -> None:
    """No boot-path file may run the ticket writer.

    ``index_occ_tickets`` is the only thing that writes unmasked ticket PII into
    a digisearch index. Any executable reference to it from the seed/boot chain
    is the leak, whether it is a supervisord command, a shell ``exec``, or a
    Dockerfile COPY of a wrapper script.
    """
    offenders = []
    for path in _boot_chain_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:  # binary asset in the container dir
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "index_occ_tickets" not in line:
                continue
            # Prose is fine; only an invocation is the problem. A reference in a
            # comment or in a marker/export name cannot run anything.
            stripped = line.strip()
            if stripped.startswith("#") or stripped.startswith("REM "):
                continue
            offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")

    assert not offenders, (
        "scripts.index_occ_tickets is reachable from the stack boot path "
        "(DIG-1438). It writes unmasked Zammad ticket bodies and sender/subject "
        "metadata into occ_tickets, and ZAMMAD_API_TOKEN is present in the live "
        "Worker env, so a boot would refill the collection:\n  " + "\n  ".join(offenders)
    )


def test_no_ticket_seed_program_in_supervisord() -> None:
    """supervisord must not declare a program that seeds or reads occ_tickets."""
    offenders = []
    for lineno, line in enumerate(SUPERVISORD.read_text(encoding="utf-8").splitlines(), 1):
        stripped = line.strip()
        if stripped.startswith("#"):
            continue
        if stripped.startswith("[program:") and "occ_tickets" in stripped:
            offenders.append(f"{SUPERVISORD.relative_to(REPO_ROOT)}:{lineno}: {stripped}")
        if stripped.startswith("command=") and "occ_tickets" in stripped:
            offenders.append(f"{SUPERVISORD.relative_to(REPO_ROOT)}:{lineno}: {stripped}")

    assert not offenders, (
        "supervisord.conf declares a program that touches occ_tickets. That boot "
        "step repopulated the collection with unmasked ticket PII (DIG-1438):\n  "
        + "\n  ".join(offenders)
    )


def test_no_occ_program_autostarts() -> None:
    """No OCC-related program may carry ``autostart=true``.

    ``seed_occ_tickets`` was the only one, but the acceptance criterion is
    broader: no program whose name mentions occ may be started automatically,
    because that is the whole shape of the re-import route.
    """
    text = SUPERVISORD.read_text(encoding="utf-8")
    blocks = re.split(r"^\[", text, flags=re.MULTILINE)
    offenders = []
    for block in blocks:
        if not block.startswith("program:"):
            continue
        name = block.splitlines()[0].removesuffix("]").strip()
        if "occ" not in name.lower():
            continue
        if re.search(r"^autostart\s*=\s*true", block, flags=re.MULTILINE):
            offenders.append(name)

    assert not offenders, (
        "OCC-related supervisord programs must not autostart; an autostarted "
        f"ticket seeder is the DIG-1438 route: {', '.join(offenders)}"
    )


def test_ticket_seed_script_is_not_shipped() -> None:
    """``seed_occ_tickets.sh`` is gone, and nothing ships or chmods it."""
    script = CONTAINER_SCRIPTS / "seed_occ_tickets.sh"
    assert not script.exists(), (
        f"{script.relative_to(REPO_ROOT)} still exists. Delete it, or reduce it to a "
        "non-boot no-op that cannot reach scripts.index_occ_tickets."
    )

    dockerfile = DOCKERFILE.read_text(encoding="utf-8")
    offenders = [
        f"Dockerfile.digithings-stack-cloudflare:{lineno}: {line.strip()}"
        for lineno, line in enumerate(dockerfile.splitlines(), start=1)
        if "seed_occ_tickets" in line and not line.strip().startswith("#")
    ]
    assert not offenders, (
        "the Dockerfile still installs seed_occ_tickets.sh into the image (COPY or "
        "chmod). The image would carry a boot step that refills occ_tickets with "
        "unmasked ticket PII:\n  " + "\n  ".join(offenders)
    )


def test_dockerfile_has_a_rebuild_marker_for_the_removal() -> None:
    """Removing a file from an image is a content-only change wrangler cannot see.

    wrangler tags the container image by Dockerfile hash, so dropping
    ``seed_occ_tickets.sh`` needs its own rebuild marker or the v16 image — which
    still contains the seeder and its supervisord block — keeps being tagged.
    """
    assert re.search(r"^# Rebuild marker v17 ", DOCKERFILE.read_text(encoding="utf-8"), re.M), (
        "Dockerfile.digithings-stack-cloudflare has no v17 rebuild marker. The ticket "
        "seeder was removed from the image, which is a build-context change wrangler "
        "cannot detect; bump the marker or the old image is reused."
    )


@pytest.mark.parametrize(
    "rel",
    [
        # The three corpus-map blobs scripts/check_tenant_corpus_map.py compares
        # against each other. That check only proves they AGREE; all three
        # carrying the fan-out would pass it. These pin the value.
        "infra/digichat-release/compose.profile-a-bundle.override.yml",
        "apps/digithings-stack-cloudflare/wrangler.toml",
        "apps/digithings-stack-cloudflare/src/index.ts",
        # Layers that check_tenant_corpus_map.py does not read, so a promotion
        # could otherwise restore the fan-out through them unnoticed.
        "infra/digichat-release/.env.profile-a-bundle.example",
        "apps/digichat/config/examples/occ-embed.yaml",
        "apps/digichat-cloudflare/README.md",
        "docs/projects/online-compliance-center/README.md",
        "infra/digichat-digithings/README.md",
    ],
)
def test_no_layer_fans_out_to_occ_tickets(rel: str) -> None:
    """No runtime or operator-facing layer may point a tenant at ``occ_tickets``.

    ``occ_help,occ_tickets`` is the #4992 fan-out leg. PR #5192 removes it from
    ``main``; if this branch keeps it, the next develop->main promotion brings it
    back together with the boot step, and every ``/chat/occ`` answer starts
    searching a corpus that is either empty or, once the writer is reachable
    again, full of unmasked customer tickets.
    """
    path = REPO_ROOT / rel
    offenders = [
        f"{rel}:{lineno}"
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1)
        if "occ_help,occ_tickets" in line
    ]
    assert not offenders, (
        f"{rel} still fans out to occ_tickets (DIG-1380 retired the ticket corpus). "
        "Promoting this branch to main would resurrect the #4992 fan-out leg: "
        + ", ".join(offenders)
    )


def test_zammad_token_is_not_a_boot_gate() -> None:
    """The credential the writer needs must not be read by the boot chain.

    ``seed_occ_tickets.sh`` skipped cleanly when ``ZAMMAD_API_TOKEN`` was unset,
    which read like a safety interlock. It is not: the token is provisioned in
    the live Worker env (``docs/ops/SECRETS_INVENTORY.md``), so the gate is
    always open. Its removal is asserted here so a reintroduced gate cannot be
    mistaken for a reintroduced control.
    """
    offenders = []
    for path in _boot_chain_files():
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for lineno, line in enumerate(text.splitlines(), start=1):
            stripped = line.strip()
            if stripped.startswith("#"):
                continue
            if ZAMMAD_TOKEN_ENV in stripped:
                offenders.append(f"{path.relative_to(REPO_ROOT)}:{lineno}: {stripped}")

    assert not offenders, (
        f"{ZAMMAD_TOKEN_ENV} is read on the boot path. In DIG-1438's removed step "
        "it was only a presence gate on the live Zammad credential, not a control; "
        "reading it from the boot chain means the ticket writer is wired back in:\n  "
        + "\n  ".join(offenders)
    )
