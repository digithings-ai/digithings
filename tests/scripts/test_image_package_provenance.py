"""A deploy may only skip packaging when image-packages/ matches the sources.

DIG-4423 measured this: `deploy_worker.sh` skipped packaging whenever
`image-packages/` merely existed, so a `digigraph/src`-only change deployed green
three times while the packaged `digigraph-0.1.0-py3-none-any.whl` was dated the
previous day and held none of the change. The guard added to the packaging script
is content-based on purpose — git checkout stamps every source file with "now", so
an mtime rule would call a freshly cloned tree stale and force a repackage, which
rewrites the container layer digests and re-uploads ~8 layers to the registry.

The tests below therefore pin the two directions that matter: identical content
at different mtimes must agree (no false refusal), and a one-byte edit must not
(the refusal that prevents the stale ship). `--check-only` is exercised directly,
with no real `image-packages/` and no network.

The file set is git's, not the filesystem's: `digiquant/results/` is gitignored yet
present on disk the moment a local backtest runs, so a walk-and-exclude digest would
drift and force a repackage of sources that never changed. `git ls-files --cached
--others --exclude-standard` excludes it by construction and still catches a new
source file that was never `git add`ed. Those two directions are pinned too, in a
throwaway repo so the real working tree is never written to.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
import os
import subprocess
from pathlib import Path
from types import ModuleType

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "package_r5_image_inputs.py"

pytestmark = pytest.mark.unit

# The npm inputs the digichat image's npm step consumes, written out here
# instead of read from the module under test. A test that compares the
# provenance record against the function that produced it cannot see a scope
# that is too narrow: the record and the scope agree while both are wrong.
# apps/dashboard is in the set because the image copies that manifest and the
# root lockfile installs the app from it.
NPM_SCOPE_INPUTS = frozenset(
    {
        "@digithings/design",
        "@digithings/ui",
        "@digithings/digichat-ui",
        "@digithings/hero-banner",
        "dashboard",
    }
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("package_r5_image_inputs", SCRIPT)
    assert spec and spec.loader, f"cannot import {SCRIPT}"
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mod = _load()


def _tree(root: Path) -> Path:
    """A minimal package tree with deterministic content."""
    (root / "src" / "pkg").mkdir(parents=True)
    (root / "pyproject.toml").write_text(
        "[project]\nname = 'pkg'\nversion = '0.1.0'\n", encoding="utf-8"
    )
    (root / "src" / "pkg" / "__init__.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "src" / "pkg" / "graph.py").write_text(
        "def build():\n    return VALUE\n", encoding="utf-8"
    )
    return root


def _write_provenance(tmp_path: Path, paths: dict[str, Path]) -> Path:
    target = tmp_path / "PROVENANCE.json"
    target.write_text(json.dumps(mod.provenance_document(paths)), encoding="utf-8")
    return target


def _git_repo(root: Path) -> Path:
    """A throwaway repository ignoring ``results/``; nothing is ever committed."""
    root.mkdir(parents=True, exist_ok=True)
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)
    (root / ".gitignore").write_text("results/\n", encoding="utf-8")
    return root


def test_digest_ignores_mtimes(tmp_path: Path) -> None:
    """The anti-false-positive test: same bytes at different times, same digest.

    A checkout hands every file mtime "now"; if this failed, every fresh clone
    would be called stale and every deploy would repackage for nothing.
    """
    first = _tree(tmp_path / "first")
    second = _tree(tmp_path / "second")
    for path in sorted(second.rglob("*")):
        os.utime(path, (1_700_000_000, 1_700_000_000))
    assert mod.content_digest(first) == mod.content_digest(second)


def test_digest_changes_on_a_one_byte_edit(tmp_path: Path) -> None:
    root = _tree(tmp_path / "pkg")
    before = mod.content_digest(root)
    edited = root / "src" / "pkg" / "graph.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "X", encoding="utf-8")
    assert mod.content_digest(root) != before


@pytest.mark.parametrize(
    "rel",
    [
        "__pycache__/graph.cpython-312.pyc",
        "node_modules/left-pad/index.js",
        "dist/pkg-0.1.0-py3-none-any.whl",
        "build/lib/graph.py",
        ".venv/lib/python3.12/site-packages/pkg/__init__.py",
        "src/pkg.egg-info/PKG-INFO",
        ".mypy_cache/3.12/graph.meta.json",
        ".ruff_cache/0.16.10/index",
        ".pytest_cache/v/cache/nodeids",
    ],
)
def test_digest_ignores_excluded_build_and_cache_dirs(tmp_path: Path, rel: str) -> None:
    """Build output and caches are not inputs; running the tests must not drift."""
    root = _tree(tmp_path / "pkg")
    before = mod.content_digest(root)
    junk = root / rel
    junk.parent.mkdir(parents=True, exist_ok=True)
    junk.write_text("not an input\n", encoding="utf-8")
    assert mod.content_digest(root) == before


def test_check_only_passes_when_provenance_matches(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = {"digigraph": _tree(tmp_path / "digigraph")}
    target = _write_provenance(tmp_path, paths)
    assert mod.check_only(paths, target) == 0
    out = capsys.readouterr().out
    assert "matches 1 packaged input" in out


def test_check_only_exits_1_and_names_the_drifted_input(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    paths = {
        "digigraph": _tree(tmp_path / "digigraph"),
        "@digithings/ui": _tree(tmp_path / "ui"),
    }
    target = _write_provenance(tmp_path, paths)
    edited = paths["digigraph"] / "src" / "pkg" / "graph.py"
    edited.write_text(edited.read_text(encoding="utf-8") + "# digigraph change\n", encoding="utf-8")
    assert mod.check_only(paths, target) == 1
    out = capsys.readouterr().out
    assert "changed: digigraph" in out
    assert "@digithings/ui" not in out
    assert "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py" in out


def test_check_only_exits_2_when_provenance_is_missing(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """Unknown provenance is not a pass: a pre-existing dir must be rebuilt once."""
    paths = {"digigraph": _tree(tmp_path / "digigraph")}
    missing = tmp_path / "PROVENANCE.json"
    assert mod.check_only(paths, missing) == 2
    out = capsys.readouterr().out
    assert "rm -rf image-packages && python3 scripts/package_r5_image_inputs.py" in out


def test_the_writer_and_check_only_agree_through_a_temporary_out(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """`main()`'s provenance step, end to end, with no uv, npm or real OUT.

    The writer was never exercised by a test — only `content_digest` and
    `check_only` were, with a hand-built document in between. So the wiring that
    actually ships (`main()` writes `OUT/PROVENANCE.json`, a deploy reads it back)
    was the untested part, and the only thing that ever proved it was a real
    `uv build` run.
    """
    monkeypatch.setattr(mod, "OUT", tmp_path)
    mod._write_provenance()
    target = tmp_path / "PROVENANCE.json"
    assert target.is_file(), "the writer must land OUT/PROVENANCE.json"
    document = json.loads(target.read_text(encoding="utf-8"))
    assert document["version"] == mod.PROVENANCE_VERSION
    assert document["combined"] and document["head"] is not None
    packages = document["packages"]
    assert isinstance(packages, dict) and packages, "packages must be a non-empty map"
    assert set(packages) == set(mod.input_paths()), "every packaged input must be fingerprinted"
    assert all(isinstance(value, str) and value for value in packages.values())
    # The round trip a deploy makes: write, then re-read and re-hash.
    assert mod.check_only() == 0


def test_a_gitignored_file_in_an_input_dir_does_not_change_the_digest(tmp_path: Path) -> None:
    """A local backtest writing `results/` must not force a repackage.

    This is the race an exclusion list loses: `digiquant/results/` is gitignored and
    appears on disk without any source changing. Git already knows it is not source,
    so the digest must not move — and a fallback walk (git unavailable) *would* move
    it, which is why this test also proves git is actually being consulted.
    """
    package = _git_repo(tmp_path / "repo") / "digiquant"
    package.mkdir()
    (package / "src.py").write_text("X = 1\n", encoding="utf-8")
    before = mod.content_digest(package)
    results = package / "results"
    results.mkdir()
    (results / "x.json").write_text('{"backtest": "local"}\n', encoding="utf-8")
    assert mod.content_digest(package) == before


def test_a_new_untracked_source_file_changes_the_digest(tmp_path: Path) -> None:
    """The other direction: a file git has never seen is packaged, so it counts.

    `--others --exclude-standard` is the half that catches it; plain `git ls-files`
    would not, and the wheel would genuinely contain the file.
    """
    package = _git_repo(tmp_path / "repo") / "digigraph"
    package.mkdir()
    (package / "graph.py").write_text("VALUE = 1\n", encoding="utf-8")
    before = mod.content_digest(package)
    (package / "fresh.py").write_text("NEW = 2\n", encoding="utf-8")
    assert mod.content_digest(package) != before


def test_the_real_repo_ignores_results_under_digiquant() -> None:
    """The premise of the test above, asserted against the repo that actually builds.

    `git check-ignore` answers for a path that need not exist, so this holds on a
    fresh clone where no backtest has ever written `results/`.
    """
    probe = subprocess.run(
        ["git", "check-ignore", "-q", "digiquant/results/x.json"],
        cwd=REPO_ROOT,
        capture_output=True,
    )
    assert probe.returncode == 0, "digiquant/results/ is no longer gitignored"


def test_digest_falls_back_loudly_when_git_is_unavailable(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """A digest of nothing must not read as "unchanged".

    With git out of reach the walk still runs, and the warning says provenance was
    computed without it — so a refused `--check-only` is never silently explained by
    an empty digest.
    """
    root = _tree(tmp_path / "pkg")
    monkeypatch.setattr(mod, "_git_listed_files", lambda _root: None)
    digest = mod.content_digest(root)
    assert digest != hashlib.sha256().hexdigest(), "an unreadable tree must not hash to nothing"
    assert "computed without git" in capsys.readouterr().err


def _fake_npm_pack(monkeypatch: pytest.MonkeyPatch) -> list[str]:
    """Replace ``npm pack`` with a fake that records the packed workspaces."""
    packed: list[str] = []

    def fake_run(cmd: list[str], *, cwd: Path | None = None) -> None:
        if cmd[:2] == ["npm", "pack"]:
            name = cmd[cmd.index("--workspace") + 1]
            dest = Path(cmd[cmd.index("--pack-destination") + 1])
            dest.mkdir(parents=True, exist_ok=True)
            (dest / f"{name.split('/')[-1]}-0.0.0.tgz").write_bytes(b"tar")
            packed.append(name)

    monkeypatch.setattr(mod, "_run", fake_run)
    return packed


def test_npm_only_packages_the_digichat_inputs_and_refuses_a_worker_deploy(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    """The digichat image installs npm tarballs; the publish lane must be able
    to package exactly those, and the tree must not read as a complete one.

    The digichat image COPYs image-packages/digichat/ and nothing else, so
    packaging it must not need uv or the wheels — a release must not depend on
    unrelated Python packages building. But a partial tree must not pass a full
    --check-only: a worker deploy built on it would ship an image without its
    wheels, which is the stale ship the check exists to refuse.
    """
    monkeypatch.setattr(mod, "OUT", tmp_path)
    packed = _fake_npm_pack(monkeypatch)

    assert mod.main(["--npm-only"]) == 0
    assert sorted(packed) == sorted(mod.NPM_PACKAGES), (
        "every npm workspace the image installs must be packed"
    )
    npm_dir = tmp_path / "digichat" / "npm"
    assert npm_dir.is_dir() and any(npm_dir.iterdir()), "the npm tarballs must land"
    assert (tmp_path / "digichat" / "manifests" / "ui" / "package.json").is_file(), (
        "the workspace manifests the Dockerfile COPYs must land"
    )

    document = json.loads((tmp_path / "PROVENANCE.json").read_text(encoding="utf-8"))
    assert document["scope"] == mod.NPM_SCOPE, (
        "a partial tree must say it is partial, or a reader cannot tell it "
        "apart from a complete one"
    )
    assert set(mod.npm_input_paths()) == set(NPM_SCOPE_INPUTS), (
        "the npm scope must cover every manifest the image copies, apps/dashboard included"
    )
    assert set(document["packages"]) == set(NPM_SCOPE_INPUTS), (
        "the record must cover exactly the inputs that were packaged"
    )

    # The npm-scoped check passes on this tree...
    assert mod.check_only(mod.npm_input_paths()) == 0
    # ...and the full check refuses it: a worker deploy must not find a
    # complete tree here.
    capsys.readouterr()
    assert mod.check_only() == 1
    refusal = capsys.readouterr().out
    missing = [line for line in refusal.splitlines() if line.strip().startswith("missing:")]
    assert missing, "the refusal must say what is missing"
    assert "dashboard" not in missing[0], "the refusal must not name a manifest the image does copy"


@pytest.mark.parametrize(
    "manifest_key",
    ["dashboard", "ui"],
    ids=["dashboard-manifest", "ui-manifest-control"],
)
def test_the_npm_scope_sees_a_changed_workspace_manifest(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, manifest_key: str
) -> None:
    """A manifest the image copies must sit inside the npm freshness scope.

    The digichat Dockerfile COPYs the dashboard manifest out of
    ``image-packages/digichat/`` and the root lockfile installs that app from
    it, so a change to ``apps/dashboard/package.json`` makes the packaged tree
    stale. With the dashboard outside the scope the npm-scoped check answered
    "ok" for exactly that change, and the stale manifest surfaced inside the
    image as an ``npm ci`` mismatch instead of the check's own message.

    The ``ui`` case is the control: it was inside the scope all along, so it
    proves the comparator fires and the dashboard zero is a scope hole rather
    than a dead check.
    """
    monkeypatch.setattr(mod, "OUT", tmp_path)
    _fake_npm_pack(monkeypatch)
    assert mod.main(["--npm-only"]) == 0

    real_digest = mod.content_digest
    changed_root = mod.NPM_MANIFESTS[manifest_key].parent

    def digest_with_a_change(root: Path) -> str:
        digest = real_digest(root)
        return "0" * 64 if root == changed_root else digest

    monkeypatch.setattr(mod, "content_digest", digest_with_a_change)
    assert mod.check_only(mod.npm_input_paths()) == 1, (
        f"a changed {manifest_key} manifest must make the npm-scoped check refuse"
    )
