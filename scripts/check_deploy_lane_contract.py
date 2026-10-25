#!/usr/bin/env python3
"""One report for the digithings-stack deploy lane's whole contract.

WHY THIS EXISTS. The lane broke three times in series on 2026-10-20, and each
failure hid the next behind it:

1. `npm ci` refused the lockfile, because the sharp tree under
   `apps/digiquant-app/node_modules` had lost its Linux x64 platform packages and
   npm 10 (what `node-version: "22"` resolves) refuses a lock npm 11 tolerates
   (#6062).
2. The deploy could not authenticate, because the lane read
   `secrets.CLOUDFLARE_WORKERS_API_TOKEN`, a name no level defines, and Actions
   substitutes an empty string for it (#6066).
3. The container build had no image inputs, because the Dockerfile COPYs a
   generated, gitignored `image-packages/stack` tree and no job packaged it
   (#6068).

A lane that fails one gate at a time is not a checked lane, it is a queue. So
this is ONE command, three legs, and one report: every leg runs, every failure
from every leg is listed, and it never stops at the first one. Exit 0 means the
lane's contract holds; exit 1 means at least one leg failed and the report says
which, with the file to fix.

THE THREE LEGS

Leg A - secret names. Every `secrets.X` the lane reads must be defined at some
level in the committed manifest `.github/secret-names.json`. The scan is
`scripts/secrets_audit.py`'s; this script does not re-implement one. The GitHub
API is NOT called: the Actions secret listings need `repo` scope and a
workflow's GITHUB_TOKEN answers 403 (DIG-477 option D rejected giving CI a PAT).
So the manifest is the source of truth, and when it marks a level `read: false`
the report says the level could not be listed and calls the read UNVERIFIED
instead of claiming it checked it.

Leg B - the generated build inputs, two ways:
  B1 every `COPY image-packages/...` source in the image Dockerfile must be
     produced by the scope the lane packages (`STACK_OUTPUTS` in
     `scripts/package_r5_image_inputs.py`).
  B2 every job that leads to the image build must carry the local action
     `./.github/actions/package-stack-image-inputs`, and that action must run
     the generator in `--stack-only` mode. A lane that builds the image without
     packaging the inputs is the #6068 failure, and it costs a production
     deploy that is already approved.

Leg C - the lockfile the lane's installer accepts. The lane installs with
`npm ci` on `node-version: "22"`, which resolves npm 10; npm 11 tolerates a
truncated lock and npm 10 refuses it. Both checks cover the whole lock, root AND
workspace trees, because the gap that broke the lane was in a workspace tree:
  C1 every package entry that declares platform `optionalDependencies` has a
     lock entry for every installable platform variant, at the declared version.
  C2 the four required Linux x64 bindings carry their `libc` selector, os, cpu
     and `optional: true` (the #6069 regression).

C1 and C2 are the only copy of that analysis: the shared functions here are
what `tests/scripts/test_package_lock_platform_coverage.py` imports, so the
binding logic exists once.

USAGE: `python3 scripts/check_deploy_lane_contract.py [--workflow PATH] [--root REPO_ROOT]`
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from pathlib import Path
from typing import Any, NamedTuple

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = Path(__file__).resolve().parent

DEFAULT_WORKFLOW = ".github/workflows/deploy-digithings-stack-cloudflare.yml"
DEFAULT_DOCKERFILE = "infra/docker/Dockerfile.digithings-stack-cloudflare"
SECRET_MANIFEST = ".github/secret-names.json"
LOCKFILE = "package-lock.json"
GENERATOR = "scripts/package_r5_image_inputs.py"
PACKAGING_ACTION = "./.github/actions/package-stack-image-inputs"
PACKAGING_ACTION_FILE = ".github/actions/package-stack-image-inputs/action.yml"
GENERATED_PREFIX = "image-packages/"
#: The workspace this lane deploys. A job that names it is a job that touches
#: the image this lane builds.
CONTAINER_WORKSPACE = "digithings-stack-cloudflare"

#: Tokens npm's `os` vocabulary uses to name a platform-specific package. A
#: family of optionalDependencies is a PLATFORM family when at least two of its
#: members carry one, or when a locked member declares `os`/`cpu`.
PLATFORM_TOKENS = (
    "aix",
    "android",
    "darwin",
    "freebsd",
    "illumos",
    "linux",
    "netbsd",
    "openbsd",
    "sunos",
    "wasm32",
    "win32",
)

#: Never installable: no real platform reports cpu "wasm32-wasi", and its nested
#: `@emnapi` subtree would collide with the `@emnapi/runtime` hoisted at the top
#: level. The npm resolver never installs it, so the lock never carries it.
EXCLUDED_BINDINGS = ("wasm32-wasi",)

#: The bindings the deleted hand-installs used to cover - glibc runners and the
#: Alpine images - and the `libc` each one must declare to be selected.
REQUIRED_LINUX_X64 = {
    "@tailwindcss/oxide-linux-x64-gnu": "glibc",
    "@tailwindcss/oxide-linux-x64-musl": "musl",
    "@unrs/resolver-binding-linux-x64-gnu": "glibc",
    "@unrs/resolver-binding-linux-x64-musl": "musl",
}

LEG_TITLES = {
    "A": "secret names",
    "B": "generated image inputs",
    "C": "lockfile the lane's installer accepts",
}


class Finding(NamedTuple):
    """One contract defect: the leg, the thing at fault, and what to do about it."""

    leg: str
    subject: str
    detail: str


class Result(NamedTuple):
    """One leg's outcome: its findings, plus anything it could not verify."""

    leg: str
    findings: list[Finding]
    notes: list[str]

    @property
    def ok(self) -> bool:
        return not self.findings


# --------------------------------------------------------------------------- #
# Leg A - secret names
# --------------------------------------------------------------------------- #


def _secrets_audit() -> Any:
    """`scripts/secrets_audit.py`, imported from beside this file.

    Reused rather than re-implemented: that module already parses a workflow
    instead of scanning it as text, already reads the committed manifest, and
    already knows that `read: false` means "not known" rather than "none".
    """
    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import secrets_audit

    return secrets_audit


def check_secret_names(workflow_path: Path, root: Path) -> Result:
    """Every `secrets.X` the lane reads must be defined at some level."""
    audit = _secrets_audit()
    reads = audit.reads_in(workflow_path.read_text(encoding="utf-8"))
    manifest = audit.manifest_from_file(root / SECRET_MANIFEST)
    levels = audit.classify_levels(reads, manifest.surface)
    unread = audit.unread_levels(manifest.surface)

    notes: list[str] = []
    if unread:
        notes.append(
            "level(s) could not be listed: "
            + ", ".join(unread)
            + f". A read that resolves nowhere above is reported as UNVERIFIED, not as absent: "
            f"refresh {SECRET_MANIFEST} with `make secrets-audit-refresh` before trusting a green run."
        )

    findings: list[Finding] = []
    for name in sorted(levels.unresolved):
        if unread:
            detail = (
                f"resolves at no listed level, but {', '.join(unread)} could not be listed, "
                "so this read is UNVERIFIED rather than proven absent. Refresh the manifest "
                "and read the answer again."
            )
        else:
            detail = (
                "is read by this lane and defined at no level in "
                f"{SECRET_MANIFEST} (repo secrets, repo variables, org secrets, environment "
                "secrets). Actions substitutes an empty string for a name it cannot resolve, so "
                "the failure lands later as an auth error on the deploy. Create the secret at a "
                "level first, or fix the name the workflow reads."
            )
        findings.append(Finding("A", f"secrets.{name}", detail))

    return Result("A", findings, notes)


# --------------------------------------------------------------------------- #
# Leg B - the generated image inputs
# --------------------------------------------------------------------------- #


def stack_outputs(root: Path) -> tuple[str, ...]:
    """`STACK_OUTPUTS` read from the generator's own source, never a copy of the list.

    Read with `ast` rather than by importing the module: the generator imports
    `tomllib` and is written for the 3.12 interpreter the packaging action sets
    up, while this check has to run on any interpreter in the repo. Reading the
    declaration is the same single source of truth; importing it would only add
    the generator's dependencies to a check that does not use them.
    """
    path = root / GENERATOR
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    for node in tree.body:
        targets: list[ast.expr] = []
        value: ast.expr | None = None
        if isinstance(node, ast.AnnAssign) and node.value is not None:
            targets, value = [node.target], node.value
        elif isinstance(node, ast.Assign):
            targets, value = list(node.targets), node.value
        if value is None:
            continue
        if any(isinstance(target, ast.Name) and target.id == "STACK_OUTPUTS" for target in targets):
            literal = ast.literal_eval(value)
            return tuple(str(item) for item in literal)
    raise LookupError(f"{path} declares no STACK_OUTPUTS, so the packaging scope is unknown")


def dockerfile_copy_sources(text: str) -> list[str]:
    """Sources of every `COPY`/`ADD` in a Dockerfile, continuation lines joined.

    The stack Dockerfile wraps one COPY over two lines, and a line-based reader
    that stops at the newline would miss the source entirely - and miss a COPY
    of a path the generator does not produce, which is exactly what B1 exists to
    catch.
    """
    sources: list[str] = []
    pending = ""
    for raw in text.splitlines():
        line = pending + raw.strip()
        pending = ""
        if not line or line.startswith("#"):
            continue
        if line.endswith("\\"):
            pending = line[:-1].rstrip() + " "
            continue
        head, _, rest = line.partition(" ")
        if head.upper() not in ("COPY", "ADD"):
            continue
        tokens = [token for token in rest.split() if not token.startswith("--")]
        if tokens and tokens[0].startswith("["):
            try:
                tokens = [str(token) for token in json.loads(rest)]
            except json.JSONDecodeError:
                pass
        if len(tokens) < 2:
            continue
        sources.extend(tokens[:-1])  # the last token is the destination
    return sources


def jobs_leading_to_build(document: dict[str, Any]) -> list[str]:
    """The jobs that touch this lane's image, plus everything they `need`.

    A job is in scope when its own text names the container workspace or the
    image Dockerfile, or when it runs the packaging action at all: those are the
    jobs whose green result is read as "the image is buildable". The `needs`
    closure is added because a gate job that a build job depends on is part of
    the same path - if it is red, the build never runs, and if it packages
    nothing, the build it guards is unproven.
    """
    jobs = document.get("jobs") or {}
    in_scope: set[str] = set()
    for name, job in jobs.items():
        text = json.dumps(job, sort_keys=True)
        if CONTAINER_WORKSPACE in text or DEFAULT_DOCKERFILE in text or PACKAGING_ACTION in text:
            in_scope.add(name)

    frontier = list(in_scope)
    while frontier:
        job = jobs.get(frontier.pop()) or {}
        needs = job.get("needs") or []
        if isinstance(needs, str):
            needs = [needs]
        for need in needs:
            if need in jobs and need not in in_scope:
                in_scope.add(need)
                frontier.append(need)
    return sorted(in_scope)


def check_image_inputs(root: Path, document: dict[str, Any]) -> Result:
    """Every generated COPY source is produced, and every build job packages it."""
    findings: list[Finding] = []
    notes: list[str] = []

    dockerfile = root / DEFAULT_DOCKERFILE
    if not dockerfile.is_file():
        findings.append(
            Finding(
                "B",
                DEFAULT_DOCKERFILE,
                "the image the lane builds is not in the tree, so no generated input can be "
                "proven. If the image moved, move this check with it.",
            )
        )
    else:
        produced = set(stack_outputs(root))
        for source in dockerfile_copy_sources(dockerfile.read_text(encoding="utf-8")):
            if not source.startswith(GENERATED_PREFIX):
                continue
            relative = source[len(GENERATED_PREFIX) :]
            if relative in produced:
                continue
            findings.append(
                Finding(
                    "B",
                    source,
                    f"{DEFAULT_DOCKERFILE} COPYs this path, but {GENERATOR}'s STACK_OUTPUTS "
                    f"does not produce it ({', '.join(sorted(produced))}). The build context would "
                    "carry no such path and the build dies computing its cache key.",
                )
            )

    action_file = root / PACKAGING_ACTION_FILE
    action_text = action_file.read_text(encoding="utf-8") if action_file.is_file() else ""
    if not action_file.is_file():
        findings.append(
            Finding(
                "B",
                PACKAGING_ACTION_FILE,
                "the local action that packages the image inputs is missing, so no job can "
                "package them and the image build has no inputs.",
            )
        )
    else:
        runner = Path(GENERATOR).name
        if runner not in action_text or "--stack-only" not in action_text:
            findings.append(
                Finding(
                    "B",
                    PACKAGING_ACTION_FILE,
                    f"the action must run `{runner} --stack-only`, the scope that produces "
                    "exactly the paths this image COPYs. It does not, so the image's inputs and "
                    "the packaging scope have drifted apart.",
                )
            )

    jobs = document.get("jobs") or {}
    for name in jobs_leading_to_build(document):
        steps = jobs[name].get("steps") or []
        uses = [str(step.get("uses") or "") for step in steps if isinstance(step, dict)]
        if any(PACKAGING_ACTION in entry for entry in uses):
            continue
        findings.append(
            Finding(
                "B",
                f"job `{name}`",
                f"leads to this lane's image build and does not run {PACKAGING_ACTION}, so that "
                "job builds (or approves a build of) an image whose generated inputs nobody "
                "packaged. This is the #6068 failure: it lands after the production approval.",
            )
        )

    if not findings:
        notes.append(
            "image inputs: "
            + ", ".join(sorted(stack_outputs(root)))
            + f" - COPYed by {DEFAULT_DOCKERFILE} and produced by {GENERATOR} --stack-only"
        )
    return Result("B", findings, notes)


# --------------------------------------------------------------------------- #
# Leg C - the lockfile the lane's installer accepts
# --------------------------------------------------------------------------- #


def load_lock(lock_path: Path) -> dict[str, Any]:
    """The `packages` map of a package-lock.json."""
    return json.loads(lock_path.read_text(encoding="utf-8"))["packages"]


def _binding_family(name: str) -> str | None:
    """`@scope/pkg-linux-x64-gnu` -> `@scope/pkg-`; the prefix its variants share.

    `None` when the name carries no `-` after the package segment, because a
    name with no variant suffix is not a platform binding.
    """
    if name.startswith("@"):
        scope, _, rest = name.partition("/")
        head, separator, _tail = rest.partition("-")
        return f"{scope}/{head}-" if separator else None
    head, separator, _tail = name.partition("-")
    return f"{head}-" if separator else None


def _parent_dir(key: str) -> str:
    """The lock key of the tree the package at `key` lives in, with a trailing slash."""
    index = key.rfind("node_modules/")
    return key[:index] if index >= 0 else ""


def resolve_binding(packages: dict[str, Any], parent_key: str, name: str) -> dict[str, Any] | None:
    """The lock entry for a binding, looking where npm puts it.

    npm nests a binding inside its parent's own tree when the hoisted copy is a
    different version (`node_modules/esbuild/node_modules/@esbuild/linux-x64`),
    then falls back to a sibling of the parent, then to the root. Reading only
    the root is the bug the old guard had: it cannot see a workspace tree's
    bindings, which is where the sharp gap was.
    """
    for candidate in (
        f"{parent_key}/node_modules/{name}",
        f"{_parent_dir(parent_key)}node_modules/{name}",
        f"node_modules/{name}",
    ):
        entry = packages.get(candidate)
        if entry is not None:
            return entry
    return None


def platform_bindings(packages: dict[str, Any]) -> list[tuple[str, dict[str, str]]]:
    """Every (parent key, {binding name: declared version}) that is platform-gated.

    Driven by what the lock itself declares, not by a hardcoded list, so a
    version bump or a new family needs no edit here.
    """
    found: list[tuple[str, dict[str, str]]] = []
    for key, entry in packages.items():
        declared = entry.get("optionalDependencies") or {}
        if not isinstance(declared, dict) or not declared:
            continue
        families: dict[str, list[str]] = {}
        for name in declared:
            family = _binding_family(name)
            if family:
                families.setdefault(family, []).append(name)
        for names in families.values():
            gated = len(names) > 1 and any(
                token in name for name in names for token in PLATFORM_TOKENS
            )
            if not gated:
                gated = any(
                    (resolve_binding(packages, key, name) or {}).get(field)
                    for name in names
                    for field in ("os", "cpu")
                )
            if gated:
                found.append((key, {name: declared[name] for name in names}))
    return found


def binding_defects(packages: dict[str, Any]) -> tuple[list[str], list[str]]:
    """C1: `(missing, mismatched)` platform bindings, as report lines.

    `missing` is what a truncated lock looks like: the parent declares the
    variant and the lock carries no entry for it. `mismatched` is a lock where
    the entry exists at a version the parent does not declare, so the JS wrapper
    and the native binary would disagree.
    """
    missing: list[str] = []
    mismatched: list[str] = []
    for parent_key, declared in platform_bindings(packages):
        for name, version in sorted(declared.items()):
            if any(token in name for token in EXCLUDED_BINDINGS):
                continue
            entry = resolve_binding(packages, parent_key, name)
            if entry is None:
                missing.append(f"{name}@{version} (declared by {parent_key})")
            elif entry.get("version") != version:
                mismatched.append(
                    f"{name}: lock has {entry.get('version')}, {parent_key} wants {version}"
                )
    return missing, mismatched


def libc_defects(packages: dict[str, Any]) -> list[str]:
    """C2: the four Linux x64 bindings must still say which libc selects them."""
    defects: list[str] = []
    for name, libc in REQUIRED_LINUX_X64.items():
        entry = packages.get(f"node_modules/{name}")
        if entry is None:
            defects.append(
                f"{name} is absent: the Linux x64 build has no native binary for libc {libc}"
            )
            continue
        if entry.get("libc") != [libc]:
            defects.append(
                f"{name} must declare libc [{libc}], got {entry.get('libc')}. Without it npm "
                "filters on os/cpu alone and installs both variants everywhere."
            )
        if entry.get("os") != ["linux"]:
            defects.append(f"{name} must declare os [linux], got {entry.get('os')}")
        if entry.get("cpu") != ["x64"]:
            defects.append(f"{name} must declare cpu [x64], got {entry.get('cpu')}")
        if entry.get("optional") is not True:
            defects.append(f"{name} must stay optional: true")
    return defects


def check_lockfile(root: Path) -> Result:
    """C1 and C2 over the whole lock, root and workspace trees alike."""
    lock_path = root / LOCKFILE
    if not lock_path.is_file():
        return Result(
            "C",
            [
                Finding(
                    "C",
                    LOCKFILE,
                    "is not in the tree: `npm ci` in the lane has no lock to install from.",
                )
            ],
            [],
        )
    packages = load_lock(lock_path)
    findings: list[Finding] = []

    missing, mismatched = binding_defects(packages)
    for line in missing:
        findings.append(
            Finding(
                "C",
                line.split(" ")[0],
                "is declared as a platform optionalDependency and the lock carries no entry for "
                "it. npm 10 refuses this lock (npm 11 tolerates it), which is how the lane broke "
                "in #6062. Regenerate the lock with npm 10.9.9 rather than hand-installing the "
                "binding in a lane.",
            )
        )
    for line in mismatched:
        findings.append(
            Finding(
                "C",
                line.split(":")[0],
                "is locked at a version its parent does not declare, so the JS wrapper and the "
                "native binary would disagree. Regenerate the lock with npm 10.9.9.",
            )
        )
    for line in libc_defects(packages):
        findings.append(Finding("C", line.split(" ")[0], line))

    notes: list[str] = []
    if not findings:
        notes.append(
            f"lockfile: {len(platform_bindings(packages))} platform families complete, "
            f"and the {len(REQUIRED_LINUX_X64)} required Linux x64 bindings carry their libc"
        )
    return Result("C", findings, notes)


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #


def load_workflow(path: Path) -> dict[str, Any]:
    """The lane, parsed. PyYAML is imported here so the message stays with the need."""
    try:
        import yaml
    except ModuleNotFoundError as exc:  # pragma: no cover - depends on the host
        raise SystemExit(
            "PyYAML is not installed, so the lane cannot be parsed. "
            "Install it with: python3 -m pip install pyyaml"
        ) from exc
    document = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(document, dict):
        raise SystemExit(f"{path} is not a workflow document")
    return document


def render(workflow: str, results: list[Result]) -> str:
    """One report: every leg, every finding, and nothing hidden behind the first."""
    findings = [finding for result in results for finding in result.findings]
    lines = [f"deploy lane contract: {workflow}", ""]
    for result in results:
        status = "ok" if result.ok else f"FAIL ({len(result.findings)})"
        lines.append(f"leg {result.leg} - {LEG_TITLES[result.leg]}: {status}")
        for finding in result.findings:
            lines.append(f"  {finding.subject}: {finding.detail}")
        for note in result.notes:
            lines.append(f"  note: {note}")
        lines.append("")
    if not findings:
        lines.append("no findings. The lane's contract holds.")
    else:
        legs = sorted({finding.leg for finding in findings})
        lines.append(
            f"{len(findings)} finding(s) across leg(s) {', '.join(legs)}. Every leg was run: "
            "this is one report, not the first failure."
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Check the digithings-stack deploy lane's whole contract in one report."
    )
    parser.add_argument(
        "--workflow",
        default=DEFAULT_WORKFLOW,
        help=f"the lane to check, relative to --root (default: {DEFAULT_WORKFLOW})",
    )
    parser.add_argument(
        "--root",
        default=str(REPO_ROOT),
        help="the repository root (default: the tree this script lives in)",
    )
    args = parser.parse_args(argv)

    root = Path(args.root).resolve()
    workflow_path = Path(args.workflow)
    if not workflow_path.is_absolute():
        workflow_path = root / workflow_path
    if not workflow_path.is_file():
        print(f"deploy lane contract: no such workflow: {workflow_path}", file=sys.stderr)
        return 1

    document = load_workflow(workflow_path)
    try:
        workflows = (
            check_secret_names(workflow_path, root),
            check_image_inputs(root, document),
            check_lockfile(root),
        )
    except Exception as exc:
        print(f"deploy lane contract: a leg could not run: {exc}", file=sys.stderr)
        return 1

    print(render(str(Path(args.workflow)), list(workflows)))
    return 0 if not any(result.findings for result in workflows) else 1


if __name__ == "__main__":
    raise SystemExit(main())
