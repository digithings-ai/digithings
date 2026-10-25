"""One mutant per leg of the deploy-lane contract check, and the all-at-once run.

WHAT THIS PINS. `scripts/check_deploy_lane_contract.py` exists because the
digithings-stack deploy lane broke three times in series on 2026-10-20 and each
failure hid the next: a truncated lock, then a secret name no level defines,
then an image build with no generated inputs. A check that reports the first
failure and stops has the same shape as the lane had, so every mutant here is
one defect, and the last test puts all three in one tree and requires ONE run to
report all three.

The mutants are taken from the ticket's acceptance list, in the same order:

1. a lane reading `secrets.CLOUDFLARE_WORKERS_API_TOKEN` (defined at no level)
2. a Dockerfile COPYing an `image-packages/` path the generator does not produce
3. a lane whose packaging step is removed from a job that leads to the build
4. a lock without the sharp Linux x64 platform packages
5. a lock with a `libc` selector stripped from a required Linux x64 binding
6. a clean tree
7. all three defects at once

Each mutant is applied to a COPY of the real lane, the real manifest, the real
action, the real generator and the real lock, so the test fails if the real
files stop being what the check reads.
"""

from __future__ import annotations

import importlib.util
import json
import shutil
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_deploy_lane_contract.py"

WORKFLOW = ".github/workflows/deploy-digithings-stack-cloudflare.yml"
DOCKERFILE = "infra/docker/Dockerfile.digithings-stack-cloudflare"
MANIFEST = ".github/secret-names.json"
ACTION = ".github/actions/package-stack-image-inputs/action.yml"
GENERATOR = "scripts/package_r5_image_inputs.py"
LOCK = "package-lock.json"

#: Every file the check reads, copied verbatim so a mutant is a one-line edit.
SOURCES = (WORKFLOW, DOCKERFILE, MANIFEST, ACTION, GENERATOR, LOCK)

PACKAGING_STEP = (
    '      - name: "Package the stack image inputs"\n'
    "        uses: ./.github/actions/package-stack-image-inputs\n"
)


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_deploy_lane_contract", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check() -> ModuleType:
    return _load()


@pytest.fixture
def tree(tmp_path: Path) -> Path:
    """A copy of the real lane's inputs, which each test may break."""
    for relative in SOURCES:
        source = REPO_ROOT / relative
        assert source.exists(), f"{relative} moved — update this test"
        destination = tmp_path / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)
    return tmp_path


def _edit(path: Path, old: str, new: str, *, count: int = -1) -> None:
    text = path.read_text(encoding="utf-8")
    assert old in text, f"the mutant target is gone from {path.name}: {old[:60]!r}"
    path.write_text(text.replace(old, new, count if count >= 0 else -1), encoding="utf-8")


def _report(check: ModuleType, root: Path, capsys: pytest.CaptureFixture[str]) -> tuple[int, str]:
    code = check.main(["--root", str(root), "--workflow", WORKFLOW])
    return code, capsys.readouterr().out


# --------------------------------------------------------------------------- #
# 6. The clean tree
# --------------------------------------------------------------------------- #


def test_the_clean_tree_reports_no_findings(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    code, out = _report(check, tree, capsys)
    assert code == 0, out
    assert "no findings" in out
    for leg in ("leg A", "leg B", "leg C"):
        assert f"{leg} - " in out, f"{leg} is missing from the report: {out}"
        assert f"{leg} - " in out and "FAIL" not in out.split(f"{leg} - ")[1].splitlines()[0], (
            f"{leg} failed on the current tree: {out}"
        )


# --------------------------------------------------------------------------- #
# 1. A secret name no level defines
# --------------------------------------------------------------------------- #


def test_a_secret_no_level_defines_fails_leg_a_and_is_named(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit(
        tree / WORKFLOW,
        "secrets.CLOUDFLARE_API_TOKEN",
        "secrets.CLOUDFLARE_WORKERS_API_TOKEN",
    )
    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "leg A - secret names: FAIL" in out, out
    assert "secrets.CLOUDFLARE_WORKERS_API_TOKEN" in out, out
    # The name that DOES exist must not be reported: the failure has to be the mutant.
    assert "secrets.CLOUDFLARE_API_TOKEN:" not in out, out


# --------------------------------------------------------------------------- #
# 2. A COPY of a path the generator does not produce
# --------------------------------------------------------------------------- #


def test_a_copy_of_a_path_the_generator_does_not_produce_fails_leg_b(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    dockerfile = tree / DOCKERFILE
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "\nCOPY image-packages/stack/not-a-stack-output /tmp/not-a-stack-output\n",
        encoding="utf-8",
    )
    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "leg B - generated image inputs: FAIL" in out, out
    assert "image-packages/stack/not-a-stack-output" in out, out


# --------------------------------------------------------------------------- #
# 3. The packaging step removed from a job that leads to the build
# --------------------------------------------------------------------------- #


def test_a_job_without_the_packaging_step_fails_leg_b(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    workflow = tree / WORKFLOW
    text = workflow.read_text(encoding="utf-8")
    assert text.count(PACKAGING_STEP) == 3, (
        "the lane no longer carries the packaging step in all three jobs — this test's "
        "mutant assumes the shape the check exists to keep"
    )
    workflow.write_text(text.replace(PACKAGING_STEP, "", 1), encoding="utf-8")

    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "leg B - generated image inputs: FAIL" in out, out
    assert "job `check`" in out, out
    # The other two jobs still carry it, so only the one that lost the step is named.
    assert "job `deploy`" not in out, out


# --------------------------------------------------------------------------- #
# 4 and 5. The lock
# --------------------------------------------------------------------------- #


def _drop_lock_entries(root: Path, needle: str) -> int:
    """Remove every lock entry whose key ends with `needle`, as a truncated lock would."""
    path = root / LOCK
    lock = json.loads(path.read_text(encoding="utf-8"))
    doomed = [key for key in lock["packages"] if key.endswith(needle)]
    assert doomed, f"the lock carries no entry ending with {needle} — update this mutant"
    for key in doomed:
        del lock["packages"][key]
    path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")
    return len(doomed)


def test_a_lock_without_the_sharp_linux_x64_packages_fails_leg_c(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _drop_lock_entries(tree, "@img/sharp-linux-x64")
    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "leg C - lockfile the lane's installer accepts: FAIL" in out, out
    assert "sharp-linux-x64" in out, out


def test_a_lock_with_a_stripped_libc_selector_fails_leg_c(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    path = tree / LOCK
    lock = json.loads(path.read_text(encoding="utf-8"))
    binding = "node_modules/@tailwindcss/oxide-linux-x64-gnu"
    assert binding in lock["packages"], f"{binding} is gone — update this mutant"
    lock["packages"][binding].pop("libc", None)
    path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "leg C - lockfile the lane's installer accepts: FAIL" in out, out
    assert "@tailwindcss/oxide-linux-x64-gnu" in out, out
    assert "libc" in out, out


# --------------------------------------------------------------------------- #
# 7. All three defects at once - the property this ticket exists for
# --------------------------------------------------------------------------- #


def test_all_three_defects_are_reported_in_one_run(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _edit(
        tree / WORKFLOW,
        "secrets.CLOUDFLARE_API_TOKEN",
        "secrets.CLOUDFLARE_WORKERS_API_TOKEN",
    )
    dockerfile = tree / DOCKERFILE
    dockerfile.write_text(
        dockerfile.read_text(encoding="utf-8")
        + "\nCOPY image-packages/stack/not-a-stack-output /tmp/not-a-stack-output\n",
        encoding="utf-8",
    )
    lock_path = tree / LOCK
    lock = json.loads(lock_path.read_text(encoding="utf-8"))
    binding = "node_modules/unrs-resolver/node_modules/@unrs/resolver-binding-linux-x64-gnu"
    target = (
        binding
        if binding in lock["packages"]
        else "node_modules/@unrs/resolver-binding-linux-x64-gnu"
    )
    assert target in lock["packages"], "the unrs binding is gone — update this mutant"
    lock["packages"][target].pop("libc", None)
    lock_path.write_text(json.dumps(lock, indent=2) + "\n", encoding="utf-8")

    code, out = _report(check, tree, capsys)
    assert code == 1, out
    for leg in ("leg A - secret names: FAIL", "leg B - generated image inputs: FAIL"):
        assert leg in out, out
    assert "leg C - lockfile the lane's installer accepts: FAIL" in out, out
    assert "3 finding(s) across leg(s) A, B, C" in out, (
        "one run must report every leg at once, not the first failure: " + out
    )


# --------------------------------------------------------------------------- #
# The boundary of leg B: a prerequisite that installs nothing is not asked to
# package an image it never touches.
# --------------------------------------------------------------------------- #


def test_only_prerequisites_that_install_the_workspace_must_package(
    check: ModuleType, tree: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A `needs` job is in scope only when it runs `npm ci`.

    Widening the rule to every prerequisite would demand generated image inputs
    from a label or policy check, and a false failure is the fastest way to get
    a check deleted. Narrowing it to none would let a real installer on the
    build path skip the packaging. Both directions are asserted here.
    """
    workflow = tree / WORKFLOW
    text = workflow.read_text(encoding="utf-8")
    needs = "    needs: [check-deploy-gate]\n"
    assert needs in text, "the deploy job's `needs` moved — update this test"
    text = text.replace(needs, "    needs: [check-deploy-gate, policy, prereq]\n")
    text += (
        "\n  policy:"
        "\n    runs-on: ubuntu-latest"
        "\n    steps:"
        "\n      - run: echo policy"
        "\n  prereq:"
        "\n    runs-on: ubuntu-latest"
        "\n    steps:"
        "\n      - run: npm ci"
        "\n"
    )
    workflow.write_text(text, encoding="utf-8")

    code, out = _report(check, tree, capsys)
    assert code == 1, out
    assert "job `prereq`" in out, f"a prerequisite that runs npm ci must package: {out}"
    assert "job `policy`" not in out, (
        f"a prerequisite that installs nothing must not be asked: {out}"
    )
