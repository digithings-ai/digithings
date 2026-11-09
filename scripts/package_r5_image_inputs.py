#!/usr/bin/env python3
"""Build the artifacts the R5 Dockerfiles install.

The images no longer COPY sibling module trees. This script, run from the
repo root before ``docker build``, turns the workspace into wheels, a
frozen requirements set (``uv export --frozen`` of the root lock), npm
tarballs for the digichat packages, and the runner payload those images
lay out at the paths they already execute.

Output is ``image-packages/`` (gitignored). It is not a registry and it
does not push an image.

The stack image's tenant seed corpus is an R6 subject. It is staged from the
mono tree by default; ``--tenant-seeds-dir`` (or ``DIGI_TENANT_SEEDS_DIR``)
points it at a checkout of a verified ``tenants-v*`` tag produced by
``scripts/fetch_tenant_seeds.sh``. The provenance records which source was
used, the tag and commit, and a content digest.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import tomllib
from datetime import datetime, timezone
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
OUT = REPO / "image-packages"
#: Written last by ``main()``. The path is resolved from ``OUT`` at call time, not
#: frozen here, so monkeypatching ``OUT`` in a test exercises the whole round trip.
PROVENANCE_NAME = "PROVENANCE.json"
PROVENANCE = OUT / PROVENANCE_NAME
PROVENANCE_VERSION = 1

# Extras match the install lines these Dockerfiles had when they copied source.
STACK_PACKAGES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("digibase", ()),
    ("digikey", ()),
    ("digitrace", ("tracing",)),
    ("digillm", ()),
    ("digigraph", ("mcp",)),
    ("digifetch", ()),
    ("digibot", ()),
    ("digisearch", ("server", "ingestion", "chroma", "web-search", "embedding-multilingual")),
    ("digivault", ("service",)),
)
RUNNER_EXPORTS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("digiquant", ("prices", "research", "nautilus")),
    ("digigraph", ("checkpoint-postgres",)),
)
RUNNER_WHEELS = (
    "digibase",
    "digikey",
    "digifetch",
    "digiquant",
    "digigraph",
    "digillm",
    "digitrace",
)
RUNNER_WHEEL_EXTRAS: dict[str, tuple[str, ...]] = {
    "digiquant": ("prices", "research", "nautilus"),
    "digigraph": ("checkpoint-postgres",),
}
NPM_PACKAGES = (
    "@digithings/design",
    "@digithings/ui",
    "@digithings/digichat-ui",
    "@digithings/hero-banner",
    # apps/digichat imports the BYOK provider catalog and the page-context
    # sanitizer from here (2026-10-20): without it in the image the digichat
    # build failed with "Module not found: @digithings/catalog/...".
    "@digithings/catalog",
)
NPM_MANIFESTS = {
    "design": REPO / "packages" / "design" / "package.json",
    "ui": REPO / "packages" / "ui" / "package.json",
    "digichat-ui": REPO / "packages" / "digichat-ui" / "package.json",
    "hero-banner": REPO / "packages" / "hero-banner" / "package.json",
    "catalog": REPO / "packages" / "catalog" / "package.json",
    "dashboard": REPO / "apps" / "dashboard" / "package.json",
}
#: The scope name recorded on a provenance that covers only the npm inputs.
#: It is what lets a reader — and ``check_only`` — tell a tree packaged for one
#: image apart from a tree that is missing a changed source.
NPM_SCOPE = "npm-only"
#: The scope name recorded on a provenance that covers only the stack inputs.
#: Same purpose as ``NPM_SCOPE``, for the image that installs workspace wheels
#: and a frozen export and installs no npm tarball.
STACK_SCOPE = "stack-only"
#: The paths under ``OUT`` the stack image's Dockerfile COPYs. The stack image
#: installs no npm tarball and no runner payload, so a stack-only tree holds
#: exactly these — and the Dockerfile's COPY list is the contract this pins.
STACK_OUTPUTS = (
    "stack/requirements.txt",
    "stack/wheels",
    "stack/digisearch-seeds",
    "stack/tenant-seeds",
)
#: The stack image's tenant seed corpus. It is an R6 subject (tenant corpora +
#: seeds), so the R5 image must not COPY the source tree: the deploy lane stages
#: it here and the Dockerfile copies the staged copy. Same rule as the wheel and
#: requirements inputs - the image consumes build inputs, never a sibling tree.
TENANT_SEEDS_SOURCE = Path("apps/digithings-stack-cloudflare/container/seed")
#: The provenance key the staged corpus is fingerprinted under. It is also the
#: name ``stack_input_paths`` uses, so ``check_only`` reports drift on it.
TENANT_SEEDS_KEY = "payload:tenant-seeds"
#: Where ``--tenant-seeds-dir`` can come from when the flag is absent.
TENANT_SEEDS_ENV = "DIGI_TENANT_SEEDS_DIR"
#: The provenance record ``scripts/fetch_tenant_seeds.sh`` writes into the
#: staged tree. It is build metadata, not seed content, so it is excluded from
#: the digest: a tag-staged tree must fingerprint the same as the mono tree it
#: replaced (T19 proves parity by digest equality).
TENANT_SOURCE_NAME = ".tenants-source"
TENANT_TAG_RE = re.compile(r"^tenants-v[0-9]+\.[0-9]+\.[0-9]+$")
TENANT_COMMIT_RE = re.compile(r"^[0-9a-f]{40}$")
#: The refusal both staging paths share. An image built without a seed corpus
#: boots and serves an empty tenant index, which looks like a healthy deploy.
EMPTY_TENANT_SEEDS = "no tenant seeds; refusing to build an image with an empty /seed"
RUNNER_FILES = (
    "scripts/refresh_market_data_r2.py",
    "scripts/backfill_market_data_r2.py",
    "scripts/execution_cron_check.py",
    "scripts/digiquant_archive_checkpoints.py",
    "scripts/digiquant_checkpoint_size_gate.py",
    "config/byok-providers.json",
    "config/model-policy.json",
    "config/digiquant-model-prices.json",
    ".github/digiquant-pipeline.yml",
    ".github/workflows/pipeline-digiquant-allocation-shadow.yml",
)
RUNNER_OPT = (
    "apps/digiquant-runner/container/exec_job.py",
    "apps/digiquant-runner/container/house_chain_step.py",
    "apps/digiquant-runner/container/wake_stack.py",
    "apps/digiquant-runner/container/web_search_preflight.py",
    "apps/digiquant-runner/commands.json",
)

#: Directories the fallback digest never descends into. Only used when git cannot
#: answer: with git, ``ls-files --exclude-standard`` excludes these — and everything
#: else the repo ignores, ``digiquant/results/`` included — by construction. A list
#: kept by hand cannot win that race, which is why it is not the primary path.
EXCLUDED_DIRS = frozenset(
    {
        "__pycache__",
        ".venv",
        "node_modules",
        ".mypy_cache",
        ".ruff_cache",
        ".pytest_cache",
        "dist",
        "build",
    }
)

#: What a developer runs when `--check-only` refuses. Quoted verbatim in the
#: abort lines so the remediation is never re-derived by hand at 2am.
REMEDIATION = "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py"


def _excluded(name: str) -> bool:
    return name in EXCLUDED_DIRS or name.endswith(".egg-info")


def _git_listed_files(root: Path) -> list[Path] | None:
    """Git's answer for "which files under ``root`` are source", or None if it cannot say.

    ``--cached`` adds tracked files and ``--others --exclude-standard`` adds untracked,
    not-ignored ones — the second half matters because a brand-new source file that has
    never been ``git add``ed is still packaged by the build, and a plain ``git ls-files``
    would miss it. Git already knows what the repository ignores, so
    ``digiquant/results/``, ``__pycache__``, ``.venv``, ``node_modules``, ``dist``,
    ``build`` and ``*.egg-info`` are excluded by construction: a local backtest writing
    into ``digiquant/results/`` can no longer drift the digest and force a repackage of
    sources that did not change.

    Paths come back relative to ``root``, because git lists relative to its working
    directory. None sends the caller to the filesystem walk — git missing, or ``root``
    outside any repository.
    """
    try:
        completed = subprocess.run(
            ["git", "ls-files", "-z", "--cached", "--others", "--exclude-standard", "--", "."],
            cwd=root,
            capture_output=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    listed = [
        Path(chunk.decode("utf-8", "surrogateescape"))
        for chunk in completed.stdout.split(b"\0")
        if chunk
    ]
    return [path for path in listed if (root / path).is_file()]


def _walked_files(root: Path) -> list[Path]:
    """The fallback enumeration: a filesystem walk, minus ``EXCLUDED_DIRS``."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(name for name in dirnames if not _excluded(name))
        for filename in sorted(filenames):
            path = Path(dirpath) / filename
            if not path.is_file():  # a dangling symlink or a socket, not a file
                continue
            found.append(path.relative_to(root))
    return found


def content_digest(root: Path, exclude: tuple[str, ...] | frozenset[str] = ()) -> str:
    """sha256 over (relative POSIX path, working-tree bytes) for an input's sources.

    mtimes are deliberately absent. Git checkout stamps every source file with the
    moment of checkout, so an mtime rule would call a freshly cloned tree stale,
    force a repackage, and rewriting the inputs changes container layer digests —
    re-uploading ~8 layers against the registry. Only real content drift refuses.

    The file set is git's (see ``_git_listed_files``) and the bytes are the working
    tree's, never the index blob's: ``uv build`` packages a dirty edit, so reading the
    index would pass a tree the wheel was not built from.

    ``exclude`` drops top-level relative paths from the digest. It exists for
    ``.tenants-source``: the tag record is build metadata, so the tag-staged tree
    must fingerprint the same as the mono tree holding the same payloads.

    Without git this degrades to the old filesystem walk and says so on stderr, rather
    than returning an empty digest that reads as "unchanged".
    """
    digest = hashlib.sha256()
    if root.is_file():
        digest.update(b"file\0")
        digest.update(root.read_bytes())
        return digest.hexdigest()

    excluded = frozenset(exclude)
    listed = _git_listed_files(root)
    if listed is not None:
        listed = [path for path in listed if path.as_posix() not in excluded]
    if listed is None or not listed:
        walked = [path for path in _walked_files(root) if path.as_posix() not in excluded]
        # listed is None: git could not answer. listed == [] over a non-empty tree:
        # every file is ignored, which is not something to trust silently.
        if listed is None or walked:
            print(
                f"warning: provenance for {root} was computed without git "
                "(filesystem walk); gitignored build output under it is not detected.",
                file=sys.stderr,
            )
            listed = walked

    for relative in sorted(listed, key=lambda path: path.as_posix()):
        digest.update(relative.as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update((root / relative).read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()


def input_paths(
    tenant_seeds_dir: Path | None = None, include_tenant_seeds: bool = True
) -> dict[str, Path]:
    """Every packaged input: name -> the source path it is built from.

    ``payload:tenant-seeds`` is one of them: a full build stages the corpus from
    ``tenant_seeds_dir`` (or the mono tree), and ``check_only`` must be able to
    re-check its digest. The npm scope passes ``include_tenant_seeds=False``:
    that image installs no seed corpus and must not require R6 content to build.
    An R0 checkout has no seed tree (it is an R6 subject) and no build to
    protect, so the key is present only when a source exists or is named.
    """
    paths: dict[str, Path] = {}
    if include_tenant_seeds and (
        tenant_seeds_dir is not None or (REPO / TENANT_SEEDS_SOURCE).is_dir()
    ):
        paths[TENANT_SEEDS_KEY] = tenant_seeds_source(tenant_seeds_dir)
    for package in dict.fromkeys([name for name, _ in STACK_PACKAGES] + list(RUNNER_WHEELS)):
        paths[package] = REPO / package

    # _write_npm() packs each NPM_PACKAGES workspace and copies each NPM_MANIFESTS
    # package.json into the image. The manifest path is the only place that layout
    # is stated, so the source dir is its parent — never a guessed
    # packages/<short-name>. 2026-10-18 was a stale npm package: a packages/ui
    # import of @digithings/hero-banner that the image never packaged.
    covered: set[str] = set()
    for manifest in NPM_MANIFESTS.values():
        if not manifest.is_file():
            # R0 has no dashboard workspace; its stub is written by _write_npm
            # and carries no source to fingerprint.
            continue
        meta = json.loads(manifest.read_text(encoding="utf-8"))
        name = str(meta["name"])
        paths[name] = manifest.parent
        covered.add(name)
    unpacked = sorted(name for name in NPM_PACKAGES if name not in covered)
    if unpacked:
        raise SystemExit(
            f"npm workspace(s) {unpacked} are packed but absent from NPM_MANIFESTS; "
            "their sources would go unfingerprinted"
        )

    # The runner payload is COPYd into the image file by file. R0 does not ship
    # the R2 runner inputs, so fingerprint only the ones that exist here; the
    # payload writer skips the rest.
    for rel in RUNNER_FILES + RUNNER_OPT:
        if (REPO / rel).exists():
            paths[f"payload:{rel}"] = REPO / rel
    for rel in ("digiquant/scripts", "digisearch/seeds"):
        if (REPO / rel).is_dir():
            paths[f"payload:{rel}"] = REPO / rel
    return paths


def _git_head() -> str | None:
    try:
        head = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPO,
            capture_output=True,
            text=True,
            check=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return None
    return head.stdout.strip() or None


def _combined(packages: dict[str, str]) -> str:
    pairs = "\n".join(f"{name}:{digest}" for name, digest in sorted(packages.items()))
    return hashlib.sha256(pairs.encode("utf-8")).hexdigest()


def tenant_seeds_source(tenant_seeds_dir: Path | None = None) -> Path:
    """The tree the image's ``/seed`` is staged from, or refuse to build.

    ``tenant_seeds_dir`` is the checkout ``scripts/fetch_tenant_seeds.sh``
    produced from a verified ``tenants-v*`` tag; absent, the mono tree is the
    source (the pre-cutover default). There is deliberately no third case: an
    image built with no seed corpus starts and serves an empty tenant index,
    which reads as a healthy deploy.

    A directory holding only metadata or a README is not a corpus either: it
    must carry at least one seed document (``.md`` other than ``README.md``,
    ``.jsonl`` or ``.json``).
    """
    chosen = Path(tenant_seeds_dir) if tenant_seeds_dir is not None else REPO / TENANT_SEEDS_SOURCE
    if not chosen.is_dir():
        raise SystemExit(f"{EMPTY_TENANT_SEEDS} (source: {chosen})")
    has_payload = any(
        path.is_file()
        and path.name != TENANT_SOURCE_NAME
        and path.name.lower() not in ("readme.md", "readme")
        and path.suffix in (".jsonl", ".json", ".md")
        for path in chosen.rglob("*")
    )
    if not has_payload:
        raise SystemExit(f"{EMPTY_TENANT_SEEDS} (source: {chosen} holds no seed payload)")
    return chosen


def read_tenant_source(seed_dir: Path) -> dict[str, str]:
    """The ``tag=``/``commit=`` record the fetcher writes, validated.

    **Self-attested by design.** The record is written by
    ``scripts/fetch_tenant_seeds.sh`` after it verifies the tag; nothing in the
    staged directory can prove that happened. Packaging has no tag object and no
    history to re-run ``git verify-tag`` against — it holds a copy of the
    corpus, not the repository — so this reader checks shape, not provenance.
    The fetcher is the trust boundary; the record is evidence of what it did,
    and a hand-written copy is indistinguishable from a fetched one. Provenance
    records ``source: tag`` on that basis.
    """
    source_file = seed_dir / TENANT_SOURCE_NAME
    try:
        lines = source_file.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise SystemExit(
            f"tenant seeds dir {seed_dir} has no {TENANT_SOURCE_NAME}; refusing "
            f"an unverified seed tree (stage it with scripts/fetch_tenant_seeds.sh) ({exc})"
        ) from exc
    values: dict[str, str] = {}
    for line in lines:
        key, separator, value = line.partition("=")
        if separator:
            values[key.strip()] = value.strip()
    tag = values.get("tag", "")
    commit = values.get("commit", "")
    if not TENANT_TAG_RE.match(tag) or not TENANT_COMMIT_RE.match(commit):
        raise SystemExit(
            f"tenant seeds provenance {source_file} is malformed "
            "(want tag=tenants-vX.Y.Z and commit=<40 hex>); refusing an "
            "unverified seed tree"
        )
    return {"tag": tag, "commit": commit}


def tenant_seeds_record(tenant_seeds_dir: Path | None = None) -> dict[str, object]:
    """The provenance entry for the staged corpus: where it came from and its digest."""
    source = tenant_seeds_source(tenant_seeds_dir)
    record: dict[str, object] = {
        "source": "mono" if tenant_seeds_dir is None else "tag",
        "tag": None,
        "commit": None,
        "digest": content_digest(source, exclude=(TENANT_SOURCE_NAME,)),
    }
    if tenant_seeds_dir is not None:
        record.update(read_tenant_source(source))
    return record


def _input_digest(name: str, path: Path) -> str:
    """``content_digest`` with the tenant seed tree's build metadata excluded."""
    excludes = (TENANT_SOURCE_NAME,) if name == TENANT_SEEDS_KEY else ()
    return content_digest(path, exclude=excludes)


def provenance_document(
    paths: dict[str, Path] | None = None,
    scope: str | None = None,
    tenant_seeds_dir: Path | None = None,
) -> dict[str, object]:
    """The provenance record written next to the packaged artifacts.

    ``scope`` names the subset the record covers when it does not cover
    everything: ``"npm-only"`` for the digichat image's inputs. It is absent on
    a full record, so a reader can tell "this tree is partial" from "this tree
    is the whole thing" without comparing key sets.

    ``tenant_seeds`` names the corpus's origin (``tag`` or ``mono``) and the
    content digest, so a build can be traced to the signed tag it consumed and
    two staging paths can be proven content-identical (T19). The record is
    self-attested by the fetcher when ``source`` is ``tag``: see
    ``read_tenant_source``.
    """
    selected = (
        input_paths(tenant_seeds_dir, include_tenant_seeds=scope != NPM_SCOPE)
        if paths is None
        else paths
    )
    packages = {name: _input_digest(name, path) for name, path in sorted(selected.items())}
    document: dict[str, object] = {
        "version": PROVENANCE_VERSION,
        "packages": packages,
        "combined": _combined(packages),
        "head": _git_head(),
        "built_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if scope is not None:
        document["scope"] = scope
    if scope in (None, STACK_SCOPE):
        document["tenant_seeds"] = tenant_seeds_record(tenant_seeds_dir)
    return document


def _provenance_path() -> Path:
    """Where the record lives, resolved from ``OUT`` at call time.

    Not the module constant: a test points ``OUT`` at a temp dir and expects both the
    writer and ``check_only()`` to follow it.
    """
    return OUT / PROVENANCE_NAME


def _write_provenance(
    paths: dict[str, Path] | None = None,
    scope: str | None = None,
    tenant_seeds_dir: Path | None = None,
) -> None:
    document = provenance_document(paths, scope, tenant_seeds_dir)
    _provenance_path().write_text(json.dumps(document, indent=2) + "\n", encoding="utf-8")


def check_only(
    paths: dict[str, Path] | None = None,
    provenance: Path | None = None,
    scope: str | None = None,
    tenant_seeds_dir: Path | None = None,
) -> int:
    """0 when the packaged inputs match the sources, 1 on drift, 2 when unknown.

    ``head`` is informational only: the decision rests on content, so a different
    commit with identical inputs still passes.

    ``scope`` asks about one image's inputs only. A scoped check reads the
    scope's sources and the scope's recorded fingerprints and ignores what the
    tree carries beyond it — a tree packaged for the whole set still satisfies a
    scoped check for the stack image. It refuses a tree packaged for a DIFFERENT
    scope, and a scoped tree still fails a full check, because a partial tree
    must never read as a complete one.

    ``tenant_seeds_dir`` points the stack scope at a tag-staged corpus instead
    of the mono tree. Its provenance must agree with the packaged payload digest
    — the two are written from one read, so a disagreement is a tampered or
    hand-edited record, not drift.
    """
    target = _provenance_path() if provenance is None else provenance
    if scope is not None and paths is not None:
        raise SystemExit(
            "check_only() takes a scope OR an explicit path set, not both: a scope "
            "already says which inputs the question is about"
        )
    selected = input_paths(tenant_seeds_dir) if paths is None else paths
    if scope == STACK_SCOPE:
        selected = stack_input_paths(tenant_seeds_dir)
    elif scope == NPM_SCOPE:
        selected = npm_input_paths()
    try:
        document = json.loads(target.read_text(encoding="utf-8"))
        recorded = document["packages"]
        if document["version"] != PROVENANCE_VERSION or not isinstance(recorded, dict):
            raise ValueError(f"unsupported provenance version {document['version']!r}")
        if not all(
            isinstance(name, str) and isinstance(value, str) for name, value in recorded.items()
        ):
            raise ValueError("malformed packages table")
    except (OSError, ValueError, KeyError, TypeError) as exc:
        print(f"ABORT: cannot read usable provenance from {target} ({exc}).")
        print("  Unknown provenance is not a pass: a package dir built before this")
        print("  check existed has no fingerprints and must be regenerated once.")
        print(f"  rebuild: {REMEDIATION}")
        return 2

    recorded_scope = document.get("scope")
    if scope is not None and recorded_scope is not None and recorded_scope != scope:
        print(f"ABORT: image-packages/ was packaged for {recorded_scope}, not {scope}.")
        print("       a tree packaged for another image does not carry this one's inputs.")
        print(f"  rebuild: {REMEDIATION}")
        return 1

    tenant_record = document.get("tenant_seeds")
    if (
        scope in (None, STACK_SCOPE)
        and isinstance(tenant_record, dict)
        and TENANT_SEEDS_KEY in recorded
        and tenant_record.get("digest") != recorded[TENANT_SEEDS_KEY]
    ):
        print(f"ABORT: {target} tenant_seeds.digest disagrees with the packaged")
        print(f"       {TENANT_SEEDS_KEY}; the record was edited after it was written.")
        print(f"  rebuild: {REMEDIATION}")
        return 2

    current = {name: _input_digest(name, path) for name, path in selected.items()}
    added = sorted(set(current) - set(recorded))
    removed = sorted(set(recorded) - set(current))
    changed = sorted(
        name for name in current if name in recorded and current[name] != recorded[name]
    )
    if scope is not None:
        # A scoped check asks about the scope's inputs only: what a full tree
        # carries beyond them is not drift.
        removed = []

    # The source digest is not enough: the image COPYs the STAGED corpus, so a
    # copy swapped after packaging would ship content the record does not name.
    # A full build writes this path too, and its record must protect it.
    staged_seeds = OUT / "stack" / "tenant-seeds"
    if (
        scope != NPM_SCOPE
        and TENANT_SEEDS_KEY in recorded
        and staged_seeds.is_dir()
        and content_digest(staged_seeds, exclude=(TENANT_SOURCE_NAME,))
        != recorded[TENANT_SEEDS_KEY]
    ):
        print("ABORT: image-packages/stack/tenant-seeds does not match the recorded")
        print(f"       {TENANT_SEEDS_KEY} digest; the staged corpus changed after packaging.")
        print(f"  rebuild: {REMEDIATION}")
        return 1

    if not (added or removed or changed):
        print(f"ok: image-packages provenance matches {len(current)} packaged input(s)")
        return 0
    if recorded_scope is not None and added:
        # A tree packaged for one image is not a tree for another. The reason
        # this refuses is INCOMPLETENESS, not staleness, and a reader who is
        # told "stale" looks for a changed source instead of a missing wheel.
        if recorded_scope == NPM_SCOPE:
            print("ABORT: image-packages/ carries only the digichat image's npm inputs —")
        else:
            print(f"ABORT: image-packages/ carries only the {recorded_scope} inputs —")
        print("       it does not cover every packaged input, so a deploy built on it")
        print("       would ship an image without its wheels.")
        print(f"  missing: {', '.join(added)}")
        print(f"  rebuild: {REMEDIATION}")
        return 1
    print("ABORT: image-packages/ is stale — it would install software that is not")
    print("       the working tree, so the image would ship a stale package.")
    for label, names in (("added", added), ("removed", removed), ("changed", changed)):
        if names:
            print(f"  {label}: {', '.join(names)}")
    print(f"  rebuild: {REMEDIATION}")
    return 1


def _run(cmd: list[str], *, cwd: Path | None = None) -> None:
    subprocess.run(cmd, cwd=cwd or REPO, check=True)


def _version(package: str) -> str:
    text = (REPO / package / "pyproject.toml").read_text(encoding="utf-8")
    version = tomllib.loads(text)["project"]["version"]
    if not isinstance(version, str) or not version:
        raise SystemExit(f"{package} has no project.version")
    return version


def _export(package: str, extras: tuple[str, ...], dest: Path) -> None:
    cmd = [
        "uv",
        "export",
        "--frozen",
        "--package",
        package,
        "--no-dev",
        "--no-emit-workspace",
        "--no-hashes",
        "--no-annotate",
        "--no-header",
        "-o",
        str(dest),
    ]
    for extra in extras:
        cmd.extend(["--extra", extra])
    _run(cmd)


def _parse_req(line: str) -> tuple[str, str, str]:
    requirement, _, marker = line.partition(";")
    requirement = requirement.strip()
    marker = marker.strip()
    if "==" not in requirement or " @" in requirement or requirement.startswith("-"):
        raise SystemExit(f"unexpected export line: {line}")
    name, version = requirement.split("==", 1)
    return name.strip().lower(), version.strip(), marker


def _merge(paths: list[Path]) -> list[str]:
    """Union of frozen export lines. Same package at two versions is an error."""
    chosen: dict[tuple[str, str], str] = {}
    for path in paths:
        for raw in path.read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line:
                continue
            name, version, marker = _parse_req(line)
            key = (name, marker)
            previous = chosen.get(key)
            if previous is not None and previous != version:
                raise SystemExit(f"{name} pin {previous} conflicts with {version} ({marker})")
            chosen[key] = version
    lines: list[str] = []
    for (name, marker), version in sorted(chosen.items()):
        spec = f"{name}=={version}"
        if marker:
            spec = f"{spec} ; {marker}"
        lines.append(spec)
    return lines


def _build_wheel(package: str, dest: Path) -> Path:
    dest.mkdir(parents=True, exist_ok=True)
    before = set(dest.glob("*.whl"))
    _run(
        [
            "uv",
            "build",
            "--wheel",
            "--package",
            package,
            "--out-dir",
            str(dest),
        ]
    )
    created = set(dest.glob("*.whl")) - before
    owned = [path for path in created if path.name.startswith(package.replace("-", "_") + "-")]
    # setuptools normalizes '-' to '_' in the wheel name; the package dir does too.
    if len(owned) != 1:
        named = [path for path in created if path.name.startswith(package + "-")]
        owned = named if len(named) == 1 else sorted(created)
    if len(owned) != 1:
        raise SystemExit(f"expected one new wheel for {package}, got {[p.name for p in owned]}")
    return owned[0]


def _requirement(package: str, version: str, extras: tuple[str, ...]) -> str:
    if extras:
        bracket = ",".join(extras)
        return f"{package}[{bracket}]=={version}"
    return f"{package}=={version}"


def _write_runner_project(wheels: dict[str, Path], requirements: list[str]) -> None:
    project = OUT / "runner" / "project"
    wheel_dir = project / "wheels"
    if project.exists():
        shutil.rmtree(project)
    wheel_dir.mkdir(parents=True)
    sources: list[str] = []
    deps: list[str] = []
    for package, wheel in wheels.items():
        target = wheel_dir / wheel.name
        shutil.copy2(wheel, target)
        version = _version(package)
        deps.append(_requirement(package, version, RUNNER_WHEEL_EXTRAS.get(package, ())))
        sources.append(f'{package} = {{ path = "wheels/{wheel.name}" }}')
    deps.extend(requirements)
    dep_lines = "\n".join(f'  "{dep}",' for dep in deps)
    source_lines = "\n".join(sources)
    text = (
        "[project]\n"
        'name = "digiquant-runner-image"\n'
        'version = "0.0.0"\n'
        'description = "Install project for the runner image. '
        'Pins are uv export --frozen of the workspace lock."\n'
        'requires-python = ">=3.12"\n'
        "dependencies = [\n"
        f"{dep_lines}\n"
        "]\n"
        "\n"
        "[tool.uv]\n"
        "package = false\n"
        "\n"
        "[tool.uv.sources]\n"
        f"{source_lines}\n"
    )
    (project / "pyproject.toml").write_text(text, encoding="utf-8")
    # Lock outside the workspace so uv does not attach this project to the monorepo.
    isolated_root = Path(tempfile.mkdtemp(prefix="digiquant-runner-image-"))
    try:
        isolated = isolated_root / "project"
        shutil.copytree(project, isolated)
        _run(["uv", "lock"], cwd=isolated)
        shutil.copy2(isolated / "uv.lock", project / "uv.lock")
    finally:
        shutil.rmtree(isolated_root)


def _write_payload() -> None:
    payload = OUT / "runner" / "payload"
    if payload.exists():
        shutil.rmtree(payload)
    for rel in RUNNER_FILES:
        src = REPO / rel
        if not src.is_file():
            # R2-only runner input: R0 does not ship it, and the R0 images do
            # not run the R2 runner.
            continue
        dest = payload / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)
    opt = payload / "opt" / "runner"
    opt.mkdir(parents=True)
    for rel in RUNNER_OPT:
        src = REPO / rel
        if not src.is_file():
            continue
        shutil.copy2(src, opt / Path(rel).name)
    scripts = REPO / "digiquant" / "scripts"
    if scripts.is_dir():
        shutil.copytree(scripts, payload / "digiquant" / "scripts")


def _write_npm() -> None:
    npm_dir = OUT / "digichat" / "npm"
    manifests = OUT / "digichat" / "manifests"
    if npm_dir.exists():
        shutil.rmtree(npm_dir)
    if manifests.exists():
        shutil.rmtree(manifests)
    npm_dir.mkdir(parents=True)
    for name in NPM_PACKAGES:
        _run(["npm", "pack", "--workspace", name, "--pack-destination", str(npm_dir)])
    for key, src in NPM_MANIFESTS.items():
        dest = manifests / key
        dest.mkdir(parents=True)
        if src.is_file():
            shutil.copy2(src, dest / "package.json")
        else:
            # The dashboard app is R3; R0's lockfile has no such workspace.
            # The Dockerfile still COPYs the path, so write a stub it can read.
            (dest / "package.json").write_text(
                json.dumps(
                    {"name": f"@digithings/{key}", "version": "0.0.0", "private": True},
                    indent=2,
                )
                + "\n",
                encoding="utf-8",
            )


def npm_input_paths() -> dict[str, Path]:
    """The npm subset of :func:`input_paths` — the inputs the digichat image installs.

    The scope is what the image's npm step consumes: every workspace manifest
    the digichat Dockerfile COPYs out of ``image-packages/digichat/`` — the
    four packed workspaces plus ``apps/dashboard``, which the root lockfile
    installs from that copied manifest — together with the sources of the
    tarballs it unpacks.

    It is derived from ``NPM_MANIFESTS``, the one place that layout is
    stated, and not from ``NPM_PACKAGES``, which lists the packed workspaces
    only. A scope narrower than the tree's writes leaves a copied manifest
    unfingerprinted, and the npm-scoped freshness check then reports a stale
    tree as fresh.
    """
    manifest_sources = {manifest.parent for manifest in NPM_MANIFESTS.values()}
    return {
        name: path
        for name, path in input_paths(include_tenant_seeds=False).items()
        if path in manifest_sources
    }


def stack_input_paths(tenant_seeds_dir: Path | None = None) -> dict[str, Path]:
    """The inputs the stack image installs — the stack half of :func:`input_paths`.

    The stack image COPYs ``image-packages/stack/{requirements.txt,wheels,
    digisearch-seeds,tenant-seeds}`` and installs no npm tarball and no runner
    payload, so
    this scope covers the nine workspace packages it installs and the seed
    corpus it bakes in. The digisearch seeds are the one payload input the
    stack image reads, and they are a source tree of their own.

    ``tenant_seeds_dir`` is the verified-tag checkout from
    ``scripts/fetch_tenant_seeds.sh``; absent, the mono tree is the source.
    """
    paths = {package: REPO / package for package, _ in STACK_PACKAGES}
    paths["payload:digisearch/seeds"] = REPO / "digisearch" / "seeds"
    paths[TENANT_SEEDS_KEY] = tenant_seeds_source(tenant_seeds_dir)
    return paths


def npm_only() -> int:
    """Package only the npm inputs, for the digichat image.

    The digichat image installs npm tarballs and workspace manifests. It
    installs no wheel, so packaging the wheels would make the publish lane
    depend on tools (uv) and on a network the image does not need, and it would
    make a release depend on unrelated Python packages building.

    The provenance written here covers ONLY these inputs and says so, so a full
    ``--check-only`` still refuses this tree for a worker deploy: a partial tree
    must never read as a complete one.
    """
    _write_npm()
    _write_provenance(npm_input_paths(), scope=NPM_SCOPE)
    print(f"wrote {OUT / 'digichat'} (npm inputs only)")
    print("  the stack and runner inputs are NOT in this tree; a worker deploy")
    print("  needs the full generator:")
    print(f"    {REMEDIATION}")
    return 0


def stack_only(tenant_seeds_dir: Path | None = None) -> int:
    """Package only the stack image's inputs.

    The stack image installs nine workspace wheels, the frozen export of their
    dependency set and the digisearch seeds. It installs no npm tarball and no
    runner payload, so packaging those would make a production deploy depend on
    tools and on a network the image does not use: the runner project alone
    runs a fresh ``uv lock`` against PyPI, and the npm step packs five
    workspaces the image never installs.

    The tenant seed corpus comes from ``tenant_seeds_dir`` when given — a
    checkout ``scripts/fetch_tenant_seeds.sh`` verified against the release
    signing key — and from the mono tree otherwise. The source is resolved
    before ``OUT`` is removed, so a missing corpus cannot wipe a good tree.

    The provenance written here covers ONLY these inputs and says so, so a full
    ``--check-only`` still refuses this tree: a partial tree must never read as
    a complete one.
    """
    tenant_seeds = tenant_seeds_source(tenant_seeds_dir)
    if OUT.exists():
        shutil.rmtree(OUT)
    stack_wheels = OUT / "stack" / "wheels"
    stack_wheels.mkdir(parents=True)
    for package, _extras in STACK_PACKAGES:
        _build_wheel(package, stack_wheels)
    export_dir = OUT / "exports"
    export_dir.mkdir(parents=True)
    stack_exports: list[Path] = []
    for package, extras in STACK_PACKAGES:
        dest = export_dir / f"stack-{package}.txt"
        _export(package, extras, dest)
        stack_exports.append(dest)
    stack_req = OUT / "stack" / "requirements.txt"
    stack_req.write_text("\n".join(_merge(stack_exports)) + "\n", encoding="utf-8")
    seeds = REPO / "digisearch" / "seeds"
    shutil.copytree(seeds, OUT / "stack" / "digisearch-seeds")
    shutil.copytree(tenant_seeds, OUT / "stack" / "tenant-seeds")
    # Last, so the record describes the artifacts on disk.
    _write_provenance(
        stack_input_paths(tenant_seeds_dir), scope=STACK_SCOPE, tenant_seeds_dir=tenant_seeds_dir
    )
    print(f"wrote {OUT / 'stack'} (stack inputs only)")
    print("  the npm and runner inputs are NOT in this tree; a worker deploy")
    print("  needs the full generator:")
    print(f"    {REMEDIATION}")
    return 0


def resolve_tenant_seeds_dir(explicit: str | None) -> Path | None:
    """The ``--tenant-seeds-dir`` value, falling back to the environment.

    An explicit flag wins over ``DIGI_TENANT_SEEDS_DIR``, and an empty variable
    is the same as unset: an accidental ``export DIGI_TENANT_SEEDS_DIR=`` must
    not turn into ``Path('.')`` and fingerprint the repository as a seed tree.
    """
    value = explicit if explicit is not None else os.environ.get(TENANT_SEEDS_ENV, "")
    value = (value or "").strip()
    if not value:
        return None
    return Path(value).expanduser()


def main(argv: list[str] | None = None) -> int:
    args = sys.argv[1:] if argv is None else argv
    check = False
    scope: str | None = None
    tenant_seeds_arg: str | None = None
    index = 0
    while index < len(args):
        arg = args[index]
        if arg == "--check-only":
            check = True
        elif arg == "--npm-only":
            if scope is not None and scope != NPM_SCOPE:
                raise SystemExit(
                    f"--{scope} and --npm-only ask for two different images' inputs; "
                    "package one image at a time"
                )
            scope = NPM_SCOPE
        elif arg == "--stack-only":
            if scope is not None and scope != STACK_SCOPE:
                raise SystemExit(
                    f"--{scope} and --stack-only ask for two different images' inputs; "
                    "package one image at a time"
                )
            scope = STACK_SCOPE
        elif arg == "--tenant-seeds-dir":
            if index + 1 >= len(args):
                raise SystemExit("--tenant-seeds-dir needs a PATH")
            tenant_seeds_arg = args[index + 1]
            index += 1
        elif arg.startswith("--tenant-seeds-dir="):
            tenant_seeds_arg = arg.split("=", 1)[1]
        else:
            raise SystemExit(
                f"unknown argument(s): {' '.join(args)} "
                "(want --check-only, --npm-only, --stack-only or --tenant-seeds-dir PATH)"
            )
        index += 1
    tenant_seeds = resolve_tenant_seeds_dir(tenant_seeds_arg)
    if tenant_seeds is not None and scope == NPM_SCOPE:
        raise SystemExit(
            "--tenant-seeds-dir stages the stack image's /seed, not an npm input; "
            "drop it from a digichat-only build"
        )
    if check:
        return check_only(scope=scope, tenant_seeds_dir=tenant_seeds)
    if scope == NPM_SCOPE:
        return npm_only()
    if scope == STACK_SCOPE:
        return stack_only(tenant_seeds)

    # Resolve before the tree is removed: a missing corpus must not destroy a
    # previously good image-packages/.
    staged_seeds = tenant_seeds_source(tenant_seeds)
    if OUT.exists():
        shutil.rmtree(OUT)
    wheel_dir = OUT / "wheels"
    wheel_dir.mkdir(parents=True)
    built: dict[str, Path] = {}
    packages = list(dict.fromkeys([name for name, _ in STACK_PACKAGES] + list(RUNNER_WHEELS)))
    for package in packages:
        built[package] = _build_wheel(package, wheel_dir)

    stack_exports: list[Path] = []
    export_dir = OUT / "exports"
    export_dir.mkdir()
    for package, extras in STACK_PACKAGES:
        dest = export_dir / f"stack-{package}.txt"
        _export(package, extras, dest)
        stack_exports.append(dest)
    stack_req = OUT / "stack" / "requirements.txt"
    stack_req.parent.mkdir(parents=True)
    stack_req.write_text("\n".join(_merge(stack_exports)) + "\n", encoding="utf-8")
    stack_wheels = OUT / "stack" / "wheels"
    stack_wheels.mkdir()
    for package, _extras in STACK_PACKAGES:
        shutil.copy2(built[package], stack_wheels / built[package].name)
    seeds = REPO / "digisearch" / "seeds"
    shutil.copytree(seeds, OUT / "stack" / "digisearch-seeds")
    shutil.copytree(staged_seeds, OUT / "stack" / "tenant-seeds")

    runner_exports: list[Path] = []
    for package, extras in RUNNER_EXPORTS:
        dest = export_dir / f"runner-{package}.txt"
        _export(package, extras, dest)
        runner_exports.append(dest)
    runner_req = _merge(runner_exports)
    runner_wheels = {package: built[package] for package in RUNNER_WHEELS}
    _write_runner_project(runner_wheels, runner_req)
    _write_payload()
    _write_npm()
    # Last, so the record describes the artifacts on disk. DIG-4423: this is what
    # lets deploy_worker.sh refuse a stale image-packages/ instead of trusting that
    # the directory merely exists.
    _write_provenance(tenant_seeds_dir=tenant_seeds)
    print(f"wrote {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
