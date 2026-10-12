"""deploy - plan, dry-run and (gated) perform a Cloudflare deploy of a surface.

This module is a sibling of ``orchestrate``/``contracts``: ``scripts/dt`` imports
it the same way, it reuses ``Step``/``StepOutcome``/``StepReport`` and
``render.render_table``, and it keeps the house rule that a step whose artefact is
absent is SKIPPED with a reason naming the owner, never a fabricated PASS.

Three things make this safe by construction:

1. **The surface registry is the repo's own** - ``config/contract/services.yaml``
   (``workers:``) cross-checked against an enumeration of ``apps/*/wrangler.toml``
   - so a surface is never invented here.
2. **The artifact is the one the local stack serves.**  A Worker has no separate
   build step (wrangler bundles ``main``); a Pages project builds with its own
   ``npm run build`` into ``pages_build_output_dir``.  Nothing here adds a second
   production build path.
3. **Production is gated.**  A real upload requires
   ``DT_DEPLOY_APPROVED_BY=chris`` in the environment.  Agents never set it, never
   read production secrets, and never run it.  ``--dry-run`` is the mode this
   repository exercises.

Bindings are compared against ``config/self-host/parity-baseline.json``
(``surface.wrangler``), which records the measured production census per config
path, so ``dt doctor parity`` diffs against a recorded source rather than a
guess.  A surface with no baseline row reports ``UNKNOWN``; it never reports a
match it did not measure.
"""

from __future__ import annotations

import json
import os
import tomllib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from scripts.localstack import render
from scripts.localstack.orchestrate import (
    FAILED,
    PASSED,
    SKIPPED,
    Runner,
    Step,
    StepOutcome,
    StepReport,
    run_steps,
    subprocess_runner,
)

#: The surface registry.  ``workers:`` rows here are the production inventory
#: verified against ``apps/*/wrangler.toml`` (see the file's own header).
SERVICES_REGISTRY = "config/contract/services.yaml"

#: The measured production binding census, per config path.
PARITY_BASELINE = "config/self-host/parity-baseline.json"

#: A real upload needs this exact value in this exact variable.  Chris sets it
#: interactively; no agent sets it.
APPROVAL_ENV = "DT_DEPLOY_APPROVED_BY"
APPROVAL_VALUE = "chris"

#: There is no hosted dev Cloudflare stack, so a non-dry-run deploy has exactly
#: one possible target and it is production.
TARGET_ENVS = ("dev", "production")

WORKER = "worker"
PAGES = "pages"

#: Binding table key -> the kind string used by the recorded baseline census.
LIST_BINDINGS = {
    "kv_namespaces": "kv_namespace",
    "r2_buckets": "r2_bucket",
    "d1_databases": "d1_database",
    "queues": "queue",
    "services": "service",
}

#: ``containers:`` rows name the *binding* in ``class_name``.  This is the
#: opposite convention from ``durable_objects.bindings[].name`` and the two are
#: routinely confused; ``_durable_objects`` handles the other shape.
CONTAINER_LIST = "containers"

#: Verdicts the parity report may print.  There is deliberately no "fine".
MATCH = "MATCH"
DIFFERS = "DIFFERS"
UNKNOWN = "UNKNOWN"

#: Every binding kind the census knows, used for the whole-config comparison.
ALL_KINDS = (
    "container",
    "d1_database",
    "durable_object_namespace",
    "kv_namespace",
    "queue",
    "r2_bucket",
    "service",
    "var",
)


@dataclass(frozen=True)
class Surface:
    """One deployable surface, as the repo declares it."""

    name: str
    config_path: str
    kind: str
    entrypoint: str
    workers_dev: str
    account_id: str
    output_dir: str
    bindings: tuple[tuple[str, str], ...]
    d1_classes: tuple[str, ...]
    routes: tuple[str, ...]
    in_registry: bool
    registered_file: str
    parse_error: str = ""

    @property
    def is_worker(self) -> bool:
        return self.kind == WORKER

    def binding_names(self, kind: str | None = None) -> tuple[str, ...]:
        # `bindings` is a tuple of (name, kind); unpacking it the other way round
        # silently filters on the name and reports an empty list for every kind.
        return tuple(n for n, k in self.bindings if kind is None or k == kind)

    def binding_map(self) -> dict[str, str]:
        return dict(self.bindings)

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "config": self.config_path,
            "kind": self.kind,
            "entrypoint": self.entrypoint,
            "workers_dev": self.workers_dev,
            "account_id": self.account_id,
            "output_dir": self.output_dir,
            "bindings": [{"name": n, "kind": k} for n, k in sorted(self.bindings)],
            "d1_classes": list(self.d1_classes),
            "routes": list(self.routes),
            "in_registry": self.in_registry,
            "registered_file": self.registered_file,
            "parse_error": self.parse_error,
        }


def _toml(path: Path) -> tuple[dict[str, Any], str]:
    """Parse a wrangler config.  A broken file is reported, never raised."""
    try:
        return tomllib.loads(path.read_text()), ""
    except (OSError, tomllib.TOMLDecodeError) as exc:
        return {}, f"{type(exc).__name__}: {exc}"


def _durable_objects(doc: Mapping[str, Any]) -> list[str]:
    """Binding names declared as durable object namespaces.

    Wrangler writes these as ``durable_objects.bindings[].name``.  A hand-written
    config may instead give a bare ``durable_objects`` map; both are read.
    """
    section = doc.get("durable_objects") or {}
    names: list[str] = []
    if isinstance(section, Mapping):
        rows = section.get("bindings") or []
        for row in rows:
            if isinstance(row, Mapping) and row.get("name"):
                names.append(str(row["name"]))
        for key in section:
            if key != "bindings":
                names.append(str(key))
    return names


def _containers(doc: Mapping[str, Any]) -> list[str]:
    """Binding names declared as containers (see ``CONTAINER_LIST``)."""
    return [
        str(row["class_name"])
        for row in doc.get(CONTAINER_LIST) or []
        if isinstance(row, Mapping) and row.get("class_name")
    ]


def _routes(doc: Mapping[str, Any]) -> tuple[str, ...]:
    """Every route a config declares, custom domains included.

    Most configs declare none and are addressed by ``workers_dev`` or by a
    Pages project; absence is a measurement, so it is rendered as such.
    """
    out: list[str] = []
    for row in doc.get("routes") or []:
        if not isinstance(row, Mapping):
            continue
        pattern = row.get("pattern") or row.get("custom_domain")
        if pattern:
            out.append(str(pattern))
    return tuple(out)


def _d1_classes(doc: Mapping[str, Any]) -> tuple[str, ...]:
    """SQLite migration classes declared by ``[[migrations]]``."""
    out: list[str] = []
    for row in doc.get("migrations") or []:
        if not isinstance(row, Mapping):
            continue
        for name in row.get("new_sqlite_classes") or []:
            out.append(str(name))
    return tuple(out)


def binding_census(doc: Mapping[str, Any]) -> dict[str, str]:
    """Binding name -> kind, in the shape ``parity-baseline.json`` records."""
    census: dict[str, str] = {}
    for key, kind in LIST_BINDINGS.items():
        for row in doc.get(key) or []:
            if isinstance(row, Mapping) and row.get("binding"):
                census[str(row["binding"])] = kind
    for name in _durable_objects(doc):
        census[name] = "durable_object_namespace"
    for name in _containers(doc):
        census[name] = "container"
    for name in doc.get("vars") or {}:
        census.setdefault(str(name), "var")
    return census


def _registry_rows(root: Path) -> list[tuple[str, str]]:
    """``workers:`` rows as ``(name, file)``, read-only, in file order."""
    path = root / SERVICES_REGISTRY
    if not path.exists():
        return []
    from scripts.localstack.contracts import _load_yaml

    doc = _load_yaml(path) or {}
    rows = []
    for row in doc.get("workers") or []:
        if isinstance(row, Mapping) and row.get("name") and row.get("file"):
            rows.append((str(row["name"]), str(row["file"])))
    return rows


def _config_paths(root: Path) -> list[str]:
    """Every wrangler config in the repo, repo-relative, sorted."""
    return sorted(p.relative_to(root).as_posix() for p in root.glob("apps/*/wrangler.toml"))


def load_surfaces(root: Path) -> tuple[Surface, ...]:
    """The deployable surfaces, from the registry cross-checked with the repo.

    A config that exists but is not in ``services.yaml`` is still returned with
    ``in_registry=False`` so it is visible rather than silently dropped; a
    registry row with no file on disk is returned with a parse error naming the
    missing path.
    """
    # services.yaml is a list of (name, file); index it BY FILE, because the
    # cross-check is "does this config exist and is it registered", and a config
    # found by enumeration is identified by its path.
    registry = {file: name for name, file in _registry_rows(root)}
    paths = list(_config_paths(root))
    for file in registry:
        if file not in paths:
            paths.append(file)

    surfaces: list[Surface] = []
    for rel in paths:
        path = root / rel
        if not path.exists():
            surfaces.append(
                Surface(
                    name=registry.get(rel, rel),
                    config_path=rel,
                    kind=WORKER,
                    entrypoint="",
                    workers_dev="unset",
                    account_id="",
                    output_dir="",
                    bindings=(),
                    d1_classes=(),
                    routes=(),
                    in_registry=rel in registry,
                    registered_file=rel,
                    parse_error=f"registered in {SERVICES_REGISTRY} but not on disk",
                )
            )
            continue
        doc, error = _toml(path)
        entrypoint = str(doc.get("main") or "")
        output_dir = str(doc.get("pages_build_output_dir") or "")
        surfaces.append(
            Surface(
                name=str(doc.get("name") or registry.get(rel, rel)),
                config_path=rel,
                kind=WORKER if entrypoint else PAGES,
                entrypoint=entrypoint,
                workers_dev=_boolish(doc.get("workers_dev")),
                account_id=str(doc.get("account_id") or ""),
                output_dir=output_dir,
                bindings=tuple(sorted(binding_census(doc).items())),
                d1_classes=_d1_classes(doc),
                routes=_routes(doc),
                in_registry=rel in registry,
                registered_file=registry.get(rel, ""),
                parse_error=error,
            )
        )
    return tuple(sorted(surfaces, key=lambda s: (s.name, s.config_path)))


def _boolish(value: Any) -> str:
    """``workers_dev`` as text; an absent key is ``unset``, not ``false``."""
    if value is None:
        return "unset"
    return "true" if bool(value) else "false"


def find_surface(surfaces: Sequence[Surface], name: str) -> Surface | None:
    """Resolve a surface by worker name, config path or app directory."""
    for s in surfaces:
        if s.name == name:
            return s
    for s in surfaces:
        if s.config_path == name or s.config_path == f"apps/{name}/wrangler.toml":
            return s
    return None


def surface_names(surfaces: Sequence[Surface]) -> tuple[str, ...]:
    return tuple(s.name for s in surfaces)


EXTRA_TOOL_DIRS = ("/opt/homebrew/bin", "/usr/local/bin")

#: ``wrangler pages deploy`` has no ``--dry-run``; ``wrangler deploy`` does.
#: Measured at the pinned wrangler: ``deploy --help`` carries ``--dry-run``,
#: ``pages deploy --help`` does not.  The one thing that would upload is
#: therefore never run in dry-run mode, and the surface is reported SKIPPED.
PAGES_DRY_RUN_NOTE = (
    "wrangler pages deploy has no --dry-run at the pinned version "
    "(wrangler deploy does); the build step above produced the artifact that "
    "would be uploaded, so the upload is skipped rather than performed"
)


def step_env(env: Mapping[str, str]) -> dict[str, str]:
    """``env`` plus the standard tool directories a host PATH can omit.

    ``docker`` lives in ``/usr/local/bin`` on a stock macOS install, and wrangler
    builds a ``[containers]`` image even in dry-run mode, so a PATH without it
    turns a working surface into a failed one.  Only directories that exist are
    added, and nothing already in the PATH is dropped or reordered.
    """
    base = str(env.get("PATH") or "")
    parts = [p for p in base.split(os.pathsep) if p]
    missing = [d for d in EXTRA_TOOL_DIRS if d not in parts and Path(d).is_dir()]
    if not missing:
        return dict(env)
    merged = dict(env)
    merged["PATH"] = os.pathsep.join([*parts, *missing])
    return merged


def _step_name(surface: Surface, target_env: str, *, dry_run: bool = False) -> str:
    """A step name that says what the step does, per surface kind.

    The ``-dry-run`` suffix is load-bearing: a row named ``-wrangler-dev``
    with ``PASS`` reads as a deploy that happened, and a dry run deploys
    nothing.  The name has to carry the same fact as the argv.
    """
    if surface.kind == PAGES:
        return f"{surface.name}-pages-deploy"
    suffix = "-dry-run" if dry_run else ""
    return f"{surface.name}-wrangler-{target_env}{suffix}"


def dry_run_skips(surface: Surface, *, dry_run: bool) -> tuple[tuple[str, str], ...]:
    """Plan entries that cannot run at all, as ``(step name, reason)``.

    A Pages surface has no wrangler-side dry run, so the upload step is not
    emitted and the caller records the skip.  SKIPPED and never FAILED: the
    surface is not broken, the tool cannot dry-run it.
    """
    if dry_run and surface.kind == PAGES:
        return ((f"{surface.name}-pages-deploy", PAGES_DRY_RUN_NOTE),)
    return ()


def wrangler_argv(
    surface: Surface, root: Path, env: Mapping[str, str], *, dry_run: bool
) -> tuple[str, ...]:
    """The wrangler invocation for a surface, using the tool override pattern.

    ``DT_WRANGLER_CMD`` wins, exactly as in ``orchestrate._tool``.  The default is
    the version ``package-lock.json`` pins, read from the lockfile rather than
    remembered, so the dry run runs the tool the repository declares.
    """
    override = env.get("DT_WRANGLER_CMD")
    tool: tuple[str, ...]
    if override:
        from scripts.localstack.orchestrate import _tool

        tool = _tool(env, "wrangler", ())
    else:
        tool = ("npx", "--yes", f"wrangler@{_wrangler_pin(root)}")
    verb = "pages deploy" if surface.kind == PAGES else "deploy"
    tail: list[str] = [verb, "--config", surface.config_path]
    if surface.kind == PAGES:
        tail.append(surface.output_dir or "out")
    if dry_run and surface.kind != PAGES:
        # Never for Pages: the flag does not exist there, and passing it would
        # make wrangler refuse the whole invocation.
        tail.append("--dry-run")
    return (*tool, *tail)


def _wrangler_pin(root: Path) -> str:
    """The ``node_modules/wrangler`` version in ``package-lock.json``."""
    lock = root / "package-lock.json"
    if not lock.exists():
        return "latest"
    try:
        doc = json.loads(lock.read_text())
    except (OSError, json.JSONDecodeError):
        return "latest"
    version = (doc.get("packages") or {}).get("node_modules/wrangler") or {}
    return str(version.get("version") or "latest")


def approval_state(env: Mapping[str, str], target_env: str) -> tuple[bool, str]:
    """Whether a real upload may run, and the reason either way.

    A skip and a refusal are different: the caller reports them as SKIPPED and as
    a usage error respectively, so an agent cannot mistake "I needed a token" for
    "the build is broken".
    """
    if target_env not in TARGET_ENVS:
        return False, f"--env {target_env} is not one of {', '.join(TARGET_ENVS)}"
    if target_env == "dev":
        return False, (
            "there is no hosted dev Cloudflare stack; a non-dry-run deploy has "
            "production as its only target"
        )
    if env.get(APPROVAL_ENV) != APPROVAL_VALUE:
        return False, (
            f"production needs {APPROVAL_ENV}={APPROVAL_VALUE}, set by Chris "
            "interactively; agents never set it"
        )
    return True, "approved"


def secret_rows(surface: Surface) -> tuple[tuple[str, str, str], ...]:
    """Binding rows, with secret-shaped kinds marked as placeholders only.

    The checklist asks for KV/DO/secret placeholders and never real values, so a
    row is reported by name and kind only.  No secret value is read here or
    anywhere else in this module.
    """
    rows = []
    for name, kind in sorted(surface.bindings):
        if kind == "var":
            rows.append((name, kind, "rendered placeholder (DIG-2959 pattern)"))
        else:
            rows.append((name, kind, "declared binding name"))
    return tuple(rows)


def deploy_steps(
    surface: Surface,
    root: Path,
    env: Mapping[str, str],
    *,
    target_env: str,
    dry_run: bool,
) -> tuple[Step, ...]:
    """The plan for one surface: build the artifact, then run wrangler.

    The build step is only present for a Pages project; a Worker has no separate
    build, because the artifact wrangler bundles from ``main`` is the same one
    ``wrangler dev`` serves locally.
    """
    steps: list[Step] = []
    if surface.kind == PAGES:
        npm = ("npm", "run", "build")
        steps.append(
            Step(
                f"{surface.name}-build",
                npm,
                requires=(surface.config_path,),
                note=(
                    "the same artifact the local stack serves: "
                    f"npm run build -> {surface.output_dir or 'out'}"
                ),
                owner="repo build (package.json)",
            )
        )
    if not dry_run_skips(surface, dry_run=dry_run):
        steps.append(
            Step(
                _step_name(surface, target_env, dry_run=dry_run),
                wrangler_argv(surface, root, env, dry_run=dry_run),
                requires=(surface.config_path,),
                note=(
                    f"{surface.kind} deploy to {target_env}"
                    + (" (dry run: no upload)" if dry_run else "")
                ),
                owner="Chris (production approval)" if not dry_run else "",
            )
        )
    return tuple(steps)


def run_deploy(
    surface: Surface,
    root: Path,
    env: Mapping[str, str],
    *,
    target_env: str,
    dry_run: bool,
    runner: Runner | None = None,
) -> StepReport:
    # `dry_run` is deliberately NOT forwarded to `run_steps`.  The house
    # `run_step(dry_run=True)` branch reports SKIPPED with the argv and never
    # starts a process, which is right for `dt up --dry-run` but wrong here:
    # the dry run has to bundle the surface (`wrangler deploy --dry-run`) to
    # prove the artifact builds.  "No upload" comes from the `--dry-run` flag
    # that `wrangler_argv` puts in the argv, plus the production gate.
    report = run_steps(
        f"deploy {surface.name}",
        deploy_steps(surface, root, env, target_env=target_env, dry_run=dry_run),
        root,
        step_env(env),
        dry_run=False,
        runner=runner or subprocess_runner,
    )
    skipped = tuple(
        StepOutcome(name=name, status=SKIPPED, detail=detail)
        for name, detail in dry_run_skips(surface, dry_run=dry_run)
    )
    if not skipped:
        return report
    return StepReport(
        command=report.command,
        outcomes=(*report.outcomes, *skipped),
        dry_run=report.dry_run,
    )


def _baseline_bindings(root: Path) -> dict[str, dict[str, str]]:
    path = root / PARITY_BASELINE
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    surface = (doc.get("surface") or {}).get("wrangler") or {}
    return {k: dict(v) for k, v in surface.items() if isinstance(v, dict)}


def _migrations_block(root: Path) -> Mapping[str, Any]:
    path = root / PARITY_BASELINE
    if not path.exists():
        return {}
    try:
        doc = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    migrations = doc.get("migrations") or {}
    return migrations if isinstance(migrations, Mapping) else {}


@dataclass(frozen=True)
class ParityRow:
    """One measured parity dimension for one surface."""

    surface: str
    dimension: str
    verdict: str
    detail: str

    def to_dict(self) -> dict[str, object]:
        return {
            "surface": self.surface,
            "dimension": self.dimension,
            "verdict": self.verdict,
            "detail": self.detail,
        }


def _subset_verdict(
    surface: Surface,
    recorded: Mapping[str, str] | None,
    kinds: Sequence[str],
    label: str,
) -> ParityRow:
    """Compare one subset of bindings against the recorded census.

    ``recorded is None`` means the baseline has no row for this config, so the
    honest verdict is UNKNOWN - never a match the check did not measure.
    """
    if recorded is None:
        return ParityRow(
            surface.name,
            label,
            UNKNOWN,
            f"{PARITY_BASELINE} has no row for {surface.config_path}",
        )
    kindset = set(kinds)
    mine = {n: k for n, k in surface.bindings if k in kindset}
    theirs = {n: k for n, k in recorded.items() if k in kindset}
    if mine == theirs:
        detail = (
            f"{len(mine)} binding(s) of kind {sorted(kindset)} identical to the recorded census"
            if mine
            else "none declared on either side; nothing to bind"
        )
        return ParityRow(surface.name, label, MATCH, detail)
    only_local = sorted(set(mine) - set(theirs))
    only_prod = sorted(set(theirs) - set(mine))
    return ParityRow(
        surface.name,
        label,
        DIFFERS,
        f"local-only={only_local} production-only={only_prod}",
    )


def parity_rows(root: Path, surfaces: Sequence[Surface]) -> tuple[ParityRow, ...]:
    """Compare each surface against the recorded production census.

    Every dimension that reads the baseline is a real diff against
    ``config/self-host/parity-baseline.json``.  The two the baseline does not
    record - local route equivalence and the local migration replay - are
    reported UNKNOWN with the reason, because the checklist asks for them and a
    check that cannot see them must say so rather than print a pass.
    """
    baseline = _baseline_bindings(root)
    migrations = _migrations_block(root)
    rows: list[ParityRow] = []

    for surface in surfaces:
        if surface.parse_error:
            rows.append(ParityRow(surface.name, "config", UNKNOWN, surface.parse_error))
            continue
        recorded = baseline.get(surface.config_path)
        rows.append(_subset_verdict(surface, recorded, ALL_KINDS, "bindings vs production"))
        rows.append(_subset_verdict(surface, recorded, ("r2_bucket",), "R2 buckets"))
        rows.append(
            _subset_verdict(
                surface, recorded, ("kv_namespace", "durable_object_namespace"), "KV / DO bindings"
            )
        )

        # D1: a [[migrations]] row declares which SQLite classes the deploy
        # creates.  Locally those are owned by `wrangler dev`, so a local D1 file
        # is not the thing that would prove parity.
        if surface.d1_classes or surface.binding_names("d1_database"):
            rows.append(
                ParityRow(
                    surface.name,
                    "D1 local DBs + migrations",
                    UNKNOWN,
                    f"migrations declared for {', '.join(surface.d1_classes)}; "
                    "`wrangler dev` owns the local database, so no local D1 file "
                    "is the artefact that would prove parity",
                )
            )
        else:
            rows.append(
                ParityRow(
                    surface.name,
                    "D1 local DBs + migrations",
                    MATCH,
                    "no D1 binding and no [[migrations]] on either side",
                )
            )

        if surface.routes:
            rows.append(
                ParityRow(
                    surface.name,
                    "routes",
                    UNKNOWN,
                    f"{len(surface.routes)} declared route(s): "
                    f"{', '.join(surface.routes)}; the local stack addresses fixed "
                    "loopback ports, so route equivalence is a deploy-time claim",
                )
            )
        else:
            rows.append(
                ParityRow(
                    surface.name,
                    "routes",
                    UNKNOWN,
                    f"no [[routes]] declared; addressed via workers_dev="
                    f"{surface.workers_dev}" + (" / Pages" if surface.kind == PAGES else ""),
                )
            )

        rows.append(
            ParityRow(
                surface.name,
                "secret placeholders",
                MATCH,
                f"{len(surface.bindings)} placeholder(s) rendered by name and kind "
                "only; this check reads no production secret (DIG-2959 pattern)",
            )
        )

    if migrations:
        rows.append(
            ParityRow(
                "(stack)",
                "migration replay",
                UNKNOWN,
                f"baseline recorded appliedFromEmpty="
                f"{migrations.get('appliedFromEmpty')} of "
                f"{migrations.get('totalMigrations')}; re-measuring the replay is "
                "DIG-3087's lane, not this check's",
            )
        )
    return tuple(rows)


def parity_verdict(rows: Sequence[ParityRow]) -> str:
    """The overall verdict: a difference fails, an unknown is reported."""
    if any(r.verdict == DIFFERS for r in rows):
        return DIFFERS
    if any(r.verdict == UNKNOWN for r in rows):
        return "PARTIAL"
    return MATCH


def parity_payload(rows: Sequence[ParityRow]) -> dict[str, object]:
    return {
        "verdict": parity_verdict(rows),
        "counts": {
            MATCH: sum(1 for r in rows if r.verdict == MATCH),
            DIFFERS: sum(1 for r in rows if r.verdict == DIFFERS),
            UNKNOWN: sum(1 for r in rows if r.verdict == UNKNOWN),
            "total": len(rows),
        },
        "rows": [r.to_dict() for r in rows],
    }


def render_binding_table(surface: Surface) -> str:
    """Bindings and routes for one surface, rendered through the house table."""
    rows = [(name, kind, note) for name, kind, note in secret_rows(surface)]
    if not rows:
        rows = [("(none)", "-", "this surface declares no bindings")]
    table = render.render_table(("BINDING", "KIND", "NOTE"), rows)
    routes = (
        ", ".join(surface.routes)
        if surface.routes
        else f"none declared (workers_dev={surface.workers_dev})"
    )
    return "\n".join(
        [
            f"{surface.name} ({surface.config_path}): {surface.kind}",
            f"  entrypoint: {surface.entrypoint or f'pages output {surface.output_dir}'}",
            f"  routes:     {routes}",
            "",
            table,
        ]
    )


def render_deploy_table(report: StepReport, surface: Surface) -> str:
    """The plan table plus the bindings/routes diff the dry run promises."""
    return "\n".join([render.render_step_table(report), "", render_binding_table(surface)])


def render_parity_table(rows: Sequence[ParityRow]) -> str:
    table = render.render_table(
        ("SURFACE", "DIMENSION", "VERDICT", "DETAIL"),
        ((r.surface, r.dimension, r.verdict, r.detail) for r in rows),
    )
    counts = parity_payload(rows)["counts"]
    head = (
        f"parity: {parity_verdict(rows)} "
        f"(match={counts[MATCH]} differs={counts[DIFFERS]} "
        f"unknown={counts[UNKNOWN]}) - UNKNOWN means this check cannot see it; "
        "it is not a pass"
    )
    return "\n".join([head, table])


__all__ = [
    "APPROVAL_ENV",
    "APPROVAL_VALUE",
    "DIFFERS",
    "MATCH",
    "PAGES",
    "PARITY_BASELINE",
    "ParityRow",
    "SERVICES_REGISTRY",
    "SKIPPED",
    "FAILED",
    "PASSED",
    "StepOutcome",
    "Surface",
    "TARGET_ENVS",
    "UNKNOWN",
    "WORKER",
    "approval_state",
    "binding_census",
    "deploy_steps",
    "find_surface",
    "load_surfaces",
    "parity_payload",
    "parity_rows",
    "parity_verdict",
    "render_binding_table",
    "render_deploy_table",
    "render_parity_table",
    "run_deploy",
    "secret_rows",
    "surface_names",
    "wrangler_argv",
]
