"""Tests for scripts/localstack/deploy.py - the surface registry, the gated
deploy plan and the parity diff.

Every test that pins a comparison also carries the arm that must break it: a
registry row that is absent from disk, a binding present on one side only, a
missing approval token.  A guard that cannot fail is not evidence.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import json
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO))

from scripts.localstack import contracts, deploy, orchestrate  # noqa: E402


@pytest.fixture()
def root() -> Path:
    return REPO


# --------------------------------------------------------------------------
# binding_census: the extractor, against the shapes wrangler actually writes
# --------------------------------------------------------------------------


def test_census_reads_both_durable_object_shapes() -> None:
    """Wrangler writes DO bindings as `durable_objects.bindings[].name`.

    A hand-written config may give a bare `durable_objects` map.  Reading only
    one of the two silently loses real bindings, which is exactly what the
    parity diff would then report as production-only.
    """
    wrapped = {
        "durable_objects": {"bindings": [{"name": "STACK", "class_name": "DigiStackContainer"}]}
    }
    bare = {"durable_objects": {"LEGACY": {"class_name": "Legacy"}}}
    assert deploy.binding_census(wrapped) == {"STACK": "durable_object_namespace"}
    assert deploy.binding_census(bare) == {"LEGACY": "durable_object_namespace"}


def test_census_container_binding_name_is_class_name() -> None:
    """`containers:` rows name the binding in `class_name`, not `name`.

    The two binding shapes use opposite conventions in the same file; reading
    `name` off a container row yields nothing.
    """
    doc = {"containers": [{"class_name": "DigiChatContainer", "image": "x"}]}
    assert deploy.binding_census(doc) == {"DigiChatContainer": "container"}


def test_census_does_not_let_a_var_shadow_a_declared_binding_kind() -> None:
    """A var only fills a name that no structured binding already claimed."""
    doc = {
        "r2_buckets": [{"binding": "ARCHIVE", "bucket_name": "b"}],
        "vars": {"ARCHIVE": "placeholder", "DT_TARGET": "dev"},
    }
    assert deploy.binding_census(doc) == {
        "ARCHIVE": "r2_bucket",
        "DT_TARGET": "var",
    }


def test_census_reads_every_kind_it_advertises() -> None:
    doc = {
        "kv_namespaces": [{"binding": "KV", "id": "x"}],
        "r2_buckets": [{"binding": "R2", "bucket_name": "b"}],
        "d1_databases": [{"binding": "DB", "database_name": "d"}],
        "queues": [{"binding": "Q", "queue": "q"}],
        "services": [{"binding": "S", "service": "worker"}],
        "durable_objects": {"bindings": [{"name": "DO"}]},
        "containers": [{"class_name": "C"}],
        "vars": {"V": "1"},
    }
    census = deploy.binding_census(doc)
    assert census == {
        "KV": "kv_namespace",
        "R2": "r2_bucket",
        "DB": "d1_database",
        "Q": "queue",
        "S": "service",
        "DO": "durable_object_namespace",
        "C": "container",
        "V": "var",
    }
    # Every advertised kind is produced; a kind the extractor can never emit is
    # a silently dead branch of the report.
    assert set(census.values()) <= set(deploy.ALL_KINDS)
    assert set(deploy.ALL_KINDS) - set(census.values()) == set()


# --------------------------------------------------------------------------
# The repo's own registry and the real census
# --------------------------------------------------------------------------


def test_every_wrangler_config_is_registered_and_none_is_phantom(root: Path) -> None:
    """The registry and an enumeration of the repo must agree exactly.

    Either direction failing is a finding: a config the registry does not know is
    a surface nobody can deploy by name, and a registry row with no file is a
    surface that cannot be deployed at all.
    """
    surfaces = deploy.load_surfaces(root)
    assert len(surfaces) == len(deploy._config_paths(root)), (
        "a registry row has no config on disk, or a config is counted twice"
    )
    assert [s.name for s in surfaces] == sorted(s.name for s in surfaces)
    for s in surfaces:
        assert s.parse_error == "", f"{s.config_path}: {s.parse_error}"
        assert s.in_registry, f"{s.config_path} is not in {deploy.SERVICES_REGISTRY}"
        assert (root / s.config_path).exists()


def test_pages_surface_is_not_reported_as_a_broken_worker(root: Path) -> None:
    """`digithings-web` has no `main`; it is a Pages project, not a defect."""
    web = deploy.find_surface(deploy.load_surfaces(root), "digithings-web")
    assert web is not None
    assert web.kind == deploy.PAGES
    assert web.entrypoint == ""
    assert web.output_dir == "out"
    workers = [s for s in deploy.load_surfaces(root) if s.kind == deploy.WORKER]
    assert workers and all(w.entrypoint for w in workers)


def test_binding_names_filters_on_kind_not_on_name(root: Path) -> None:
    """`bindings` is a tuple of (name, kind).

    Unpacking it the other way round makes every `kind` filter return an empty
    list, which reads as "this surface declares no R2 bucket" - a false negative
    on exactly the dimension the checklist asks for.
    """
    runner = deploy.find_surface(deploy.load_surfaces(root), "digiquant-runner")
    assert runner is not None
    assert runner.binding_names("r2_bucket"), "the repo does declare ARCHIVE"
    assert "r2_bucket" not in runner.binding_names()
    assert set(runner.binding_names("r2_bucket")) <= set(runner.binding_names())


def test_surface_resolves_by_name_directory_and_path(root: Path) -> None:
    surfaces = deploy.load_surfaces(root)
    assert deploy.find_surface(surfaces, "digithings-stack").name == "digithings-stack"
    assert deploy.find_surface(surfaces, "digithings-stack-cloudflare").name == "digithings-stack"
    assert (
        deploy.find_surface(surfaces, "apps/digithings-stack-cloudflare/wrangler.toml").name
        == "digithings-stack"
    )
    assert deploy.find_surface(surfaces, "not-a-surface") is None


def test_a_registry_row_with_no_file_is_reported_not_dropped(tmp_path: Path) -> None:
    """An index built from a missing path must still surface it."""
    (tmp_path / "config/contract").mkdir(parents=True)
    (tmp_path / "config/contract/services.yaml").write_text(
        "workers:\n  - name: ghost\n    file: apps/ghost/wrangler.toml\n",
        encoding="utf-8",
    )
    (tmp_path / "config/self-host").mkdir(parents=True)
    (tmp_path / "config/self-host/parity-baseline.json").write_text(
        json.dumps({"surface": {"wrangler": {}}}), encoding="utf-8"
    )
    surfaces = deploy.load_surfaces(tmp_path)
    assert [s.name for s in surfaces] == ["ghost"]
    assert "not on disk" in surfaces[0].parse_error


# --------------------------------------------------------------------------
# The production gate
# --------------------------------------------------------------------------


def test_production_refuses_without_the_approval_token() -> None:
    ok, reason = deploy.approval_state({}, "production")
    assert ok is False
    assert deploy.APPROVAL_ENV in reason


def test_a_wrong_approver_is_not_an_approver() -> None:
    """`DT_DEPLOY_APPROVED_BY` carries a name; only Chris's unlocks a deploy."""
    for wrong in ("agent", "chris ", "CHRIS", "chris,agent", ""):
        ok, _ = deploy.approval_state({deploy.APPROVAL_ENV: wrong}, "production")
        assert ok is False, wrong


def test_the_exact_token_opens_the_production_path() -> None:
    ok, _ = deploy.approval_state({deploy.APPROVAL_ENV: deploy.APPROVAL_VALUE}, "production")
    assert ok is True


def test_dev_has_no_hosted_target_to_deploy_to() -> None:
    """A real upload has production as its only possible target."""
    ok, reason = deploy.approval_state({}, "dev")
    assert ok is False
    assert "no hosted dev" in reason


def test_an_unknown_env_is_a_usage_error() -> None:
    ok, _ = deploy.approval_state({}, "staging")
    assert ok is False


def test_no_production_secret_is_read_anywhere_in_the_module() -> None:
    """The checklist asks for placeholders and never real values."""
    source = (REPO / "scripts/localstack/deploy.py").read_text(encoding="utf-8")
    for forbidden in ("vault", "wrangler secret list", "getWorkersSecret"):
        assert forbidden not in source


# --------------------------------------------------------------------------
# The plan: same artifact, wrangler verb, dry run
# --------------------------------------------------------------------------


def test_worker_plan_has_no_separate_build_step(root: Path) -> None:
    """A Worker has no build script; wrangler bundles `main`, which is the same
    artefact `wrangler dev` serves locally.  Inventing a build step would be the
    separate production build path the brief forbids."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    steps = deploy.deploy_steps(worker, root, {}, target_env="dev", dry_run=True)
    assert [s.name for s in steps] == ["digithings-stack-wrangler-dev"]
    assert steps[0].requires == (worker.config_path,)


def test_pages_plan_builds_first_from_the_same_package_script(root: Path) -> None:
    """The build is the real work for a Pages surface; the upload is not run.

    `wrangler pages deploy` has no `--dry-run` at the pinned version, so the
    only command that could upload is not part of a dry-run plan at all.
    """
    web = deploy.find_surface(deploy.load_surfaces(root), "digithings-web")
    steps = deploy.deploy_steps(web, root, {}, target_env="dev", dry_run=True)
    assert [s.name for s in steps] == ["digithings-web-build"]
    assert steps[0].argv == ("npm", "run", "build")
    skips = deploy.dry_run_skips(web, dry_run=True)
    assert [name for name, _ in skips] == ["digithings-web-pages-deploy"]
    assert "--dry-run" in skips[0][1] and "pages deploy" in skips[0][1]
    assert deploy.dry_run_skips(web, dry_run=False) == ()


def test_dry_run_passes_the_flag_and_a_worker_uses_deploy_not_pages(root: Path) -> None:
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    argv = deploy.wrangler_argv(worker, root, {}, dry_run=True)
    assert "--dry-run" in argv
    assert "pages" not in argv
    assert argv[argv.index("deploy") + 1 :][:2] == ("--config", worker.config_path)


def test_wrangler_version_comes_from_the_lockfile(root: Path) -> None:
    """The dry run must use the version the repository pins, not a remembered one."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    argv = deploy.wrangler_argv(worker, root, {}, dry_run=True)
    lock = json.loads((root / "package-lock.json").read_text())
    pinned = lock["packages"]["node_modules/wrangler"]["version"]
    assert f"wrangler@{pinned}" in argv


def test_wrangler_override_wins(root: Path) -> None:
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    argv = deploy.wrangler_argv(
        worker, root, {"DT_WRANGLER_CMD": "/opt/homebrew/bin/wrangler --version"}, dry_run=True
    )
    assert argv[:2] == ("/opt/homebrew/bin/wrangler", "--version")


def test_a_dry_run_actually_runs_wrangler_with_the_dry_run_flag(root: Path) -> None:
    """`dt deploy --dry-run` must BUNDLE the surface; the house `dry_run=True`
    branch of `run_step` reports SKIPPED without starting a process, which would
    make the dry run vacuous — the one thing the DoD measures would never run.

    A recording runner proves the step really is invoked (non-vacuity), and the
    flag inside the argv is what forbids the upload."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    seen: list[tuple[str, ...]] = []

    def record(argv, cwd, env):
        seen.append(tuple(argv))
        return 0, "Total Upload: 0.00 KiB"

    report = deploy.run_deploy(
        worker, root, {}, target_env="dev", dry_run=True, runner=record
    )
    assert len(seen) == 1, "the dry run did not execute wrangler"
    assert "--dry-run" in seen[0]
    assert report.ok
    assert report.outcomes[0].status == orchestrate.PASSED


def test_a_dry_run_argv_carries_no_upload_past_the_dry_run_flag(root: Path) -> None:
    """Nothing in the argv may upload: `--dry-run` is the last flag wrangler
    reads, so it must be present on the deploy itself, not on a build step."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    steps = deploy.deploy_steps(worker, root, {}, target_env="dev", dry_run=True)
    wrangler_step = [s for s in steps if s.name.endswith("-wrangler-dev")][0]
    assert "--dry-run" in wrangler_step.argv
    assert "--remote" not in wrangler_step.argv
    assert "--publish" not in wrangler_step.argv


def test_a_pages_dry_run_argv_never_carries_the_unsupported_flag(root: Path) -> None:
    """`wrangler pages deploy` rejects `--dry-run`; passing it anyway would make
    wrangler refuse the whole invocation instead of skipping the upload.

    The worker arm is the positive control: the matcher must be able to find the
    flag where it does exist, so the pages zero is a fact and not a blind grep.
    """
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    web = deploy.find_surface(deploy.load_surfaces(root), "digithings-web")
    assert "--dry-run" in deploy.wrangler_argv(worker, root, {}, dry_run=True)
    assert "--dry-run" not in deploy.wrangler_argv(web, root, {}, dry_run=True)


def test_a_pages_production_run_still_emits_the_upload(root: Path) -> None:
    """The dry-run gap must not remove the deploy path: a real run still has
    one, it is just gated by the approval token, not by a missing plan entry."""
    web = deploy.find_surface(deploy.load_surfaces(root), "digithings-web")
    steps = deploy.deploy_steps(web, root, {}, target_env="production", dry_run=False)
    assert [s.name for s in steps] == ["digithings-web-build", "digithings-web-pages-deploy"]
    upload = steps[1]
    verb = upload.argv[upload.argv.index("pages deploy")]
    assert verb == "pages deploy"
    assert upload.argv[upload.argv.index("pages deploy") + 1] == "--config"
    assert web.output_dir in upload.argv
    assert "--dry-run" not in upload.argv


def test_a_pages_dry_run_is_skipped_with_the_reason_and_never_uploads(root: Path) -> None:
    """SKIPPED, never FAILED: the surface is not broken, wrangler cannot dry-run
    it.  A recording runner is the non-vacuity arm — nothing that could upload
    is ever handed to it."""
    web = deploy.find_surface(deploy.load_surfaces(root), "digithings-web")
    seen: list[tuple[str, ...]] = []

    def record(argv, cwd, env):
        seen.append(tuple(argv))
        return 0, "built"

    report = deploy.run_deploy(web, root, {}, target_env="dev", dry_run=True, runner=record)
    assert seen == [("npm", "run", "build")], seen
    upload_steps = [o for o in report.outcomes if "pages-deploy" in o.name]
    assert [o.status for o in upload_steps] == [orchestrate.SKIPPED]
    assert "--dry-run" in upload_steps[0].detail
    assert report.ok


def test_step_env_adds_only_directories_that_exist() -> None:
    """`docker` lives in `/usr/local/bin` on a stock macOS install and wrangler
    builds a `[containers]` image even in dry-run mode, so the PATH a step runs
    with has to include it.  A directory that does not exist is never added, and
    the caller's PATH survives unchanged."""
    base = {"PATH": "/usr/bin:/bin"}
    merged = deploy.step_env(base)
    parts = merged["PATH"].split(":")
    assert parts[:2] == ["/usr/bin", "/bin"], "the caller's PATH must lead"
    for directory in deploy.EXTRA_TOOL_DIRS:
        if Path(directory).is_dir():
            assert directory in parts
        else:
            assert directory not in parts
    assert deploy.step_env({})["PATH"].split(":") == list(
        d for d in deploy.EXTRA_TOOL_DIRS if Path(d).is_dir()
    )


def test_a_dry_run_runs_with_a_path_that_reaches_the_extra_tool_dirs(root: Path) -> None:
    """The step env is the merged one, so a surface with containers can find
    docker.  Pins it against the recorded runner rather than the helper alone."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    seen: list[dict[str, str]] = []

    def record(argv, cwd, env):
        seen.append(dict(env))
        return 0, "ok"

    deploy.run_deploy(worker, root, {"PATH": "/usr/bin:/bin"}, target_env="dev",
                      dry_run=True, runner=record)
    assert len(seen) == 1
    parts = seen[0]["PATH"].split(":")
    assert parts[:2] == ["/usr/bin", "/bin"]
    assert "/usr/local/bin" in parts  # docker, on this host


def test_a_missing_config_skips_the_step_naming_the_owner(root: Path, tmp_path: Path) -> None:
    """An absent artefact is SKIPPED with a reason, never a fabricated pass."""
    worker = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    outcome = orchestrate.run_step(
        deploy.deploy_steps(worker, root, {}, target_env="dev", dry_run=False)[0],
        tmp_path,
        {},
    )
    assert outcome.status == orchestrate.SKIPPED
    assert "not present" in outcome.detail
    assert outcome.status != orchestrate.PASSED


# --------------------------------------------------------------------------
# The parity diff: a real comparison, and an honest unknown
# --------------------------------------------------------------------------


def test_repo_bindings_match_the_recorded_production_census(root: Path) -> None:
    """The extractor is validated against the baseline the repo already ships.

    If this ever reports a difference, either a config changed its bindings or
    the census regressed; both are findings, and neither may be papered over with
    a PASS-shaped assertion.
    """
    rows = [
        r
        for r in deploy.parity_rows(root, deploy.load_surfaces(root))
        if r.dimension == "bindings vs production"
    ]
    assert rows, "no binding rows were produced at all"
    differs = [f"{r.surface}: {r.detail}" for r in rows if r.verdict == deploy.DIFFERS]
    assert differs == [], differs


def test_parity_is_computed_not_assumed(root: Path) -> None:
    rows = deploy.parity_rows(root, deploy.load_surfaces(root))
    payload = deploy.parity_payload(rows)
    assert payload["counts"]["total"] == len(rows)
    assert sum(payload["counts"][k] for k in (deploy.MATCH, deploy.DIFFERS, deploy.UNKNOWN)) == len(
        rows
    )
    assert deploy.parity_verdict(rows) in {deploy.MATCH, "PARTIAL", deploy.DIFFERS}


def test_a_binding_only_in_production_is_reported_as_a_difference(tmp_path: Path) -> None:
    """The diff arm that must fire: one side has a binding the other lacks."""
    _fixture_repo(
        tmp_path,
        wrangler='name = "w"\nmain = "src/index.ts"\n[vars]\nDT_TARGET = "dev"\n',
        baseline={"apps/w/wrangler.toml": {"DT_TARGET": "var", "GONE": "r2_bucket"}},
    )
    rows = deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
    binding = next(r for r in rows if r.dimension == "bindings vs production")
    assert binding.verdict == deploy.DIFFERS
    assert "GONE" in binding.detail
    assert deploy.parity_verdict(rows) == deploy.DIFFERS


def test_a_binding_only_locally_is_reported_as_a_difference(tmp_path: Path) -> None:
    _fixture_repo(
        tmp_path,
        wrangler='name = "w"\nmain = "src/index.ts"\n[vars]\nNEW_ONE = "1"\n',
        baseline={"apps/w/wrangler.toml": {"OLD_ONE": "var"}},
    )
    binding = next(
        r
        for r in deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
        if r.dimension == "bindings vs production"
    )
    assert binding.verdict == deploy.DIFFERS
    assert "NEW_ONE" in binding.detail


def test_a_surface_with_no_baseline_row_is_unknown_not_matched(tmp_path: Path) -> None:
    """A check that cannot see the subject must not report a match.

    The two baseline-dependent dimensions must be UNKNOWN.  A row that is
    UNKNOWN on every input is an empty-vs-empty trap, so the same fixture is
    also run *with* a baseline row and must come back MATCH.
    """
    baseline_dims = ("bindings vs production", "R2 buckets", "KV / DO bindings")
    _fixture_repo(tmp_path, wrangler='name = "w"\nmain = "src/index.ts"\n', baseline={})
    rows = deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
    unseen = [r for r in rows if r.dimension in baseline_dims]
    assert unseen and all(r.verdict == deploy.UNKNOWN for r in unseen)
    assert all(deploy.PARITY_BASELINE in r.detail for r in unseen)
    assert deploy.parity_verdict(rows) != deploy.MATCH

    # Control: the same surface, now recorded, matches on those dimensions.
    seen_rows = deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
    assert seen_rows  # the fixture is not empty: the rows are the subject
    (tmp_path / "config/self-host/parity-baseline.json").write_text(
        json.dumps({"surface": {"wrangler": {"apps/w/wrangler.toml": {}}}}),
        encoding="utf-8",
    )
    with_baseline = [
        r
        for r in deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
        if r.dimension in baseline_dims
    ]
    assert with_baseline and all(r.verdict == deploy.MATCH for r in with_baseline)


def test_an_identical_census_reports_match_with_the_count(tmp_path: Path) -> None:
    _fixture_repo(
        tmp_path,
        wrangler='name = "w"\nmain = "src/index.ts"\n[vars]\nA = "1"\n',
        baseline={"apps/w/wrangler.toml": {"A": "var"}},
    )
    binding = next(
        r
        for r in deploy.parity_rows(tmp_path, deploy.load_surfaces(tmp_path))
        if r.dimension == "bindings vs production"
    )
    assert binding.verdict == deploy.MATCH
    assert "1" in binding.detail


def test_declared_routes_are_read_and_rendered(root: Path) -> None:
    """The positive arm for `[[routes]]`.

    Only asserting an ABSENT route list lets a mutant that never reads the table
    survive: the repo's stack worker declares ten routes, and a routes diff that
    cannot see them is not a routes diff.
    """
    stack = deploy.find_surface(deploy.load_surfaces(root), "digithings-stack")
    assert stack is not None
    assert stack.routes, "the repo declares [[routes]] on this worker"
    assert len(stack.routes) == len(set(stack.routes)), "routes must be de-duplicated"
    table = deploy.render_binding_table(stack)
    for route in stack.routes:
        assert route in table, route
    # A control that must fire, so an empty list cannot satisfy the loop above.
    assert "graph.digithings.ai" in stack.routes


def test_routes_read_both_a_pattern_and_a_custom_domain() -> None:
    """Wrangler writes `pattern = ...` or `custom_domain = ...`; read both."""
    assert deploy._routes({"routes": [{"pattern": "a.example/*"}]}) == ("a.example/*",)
    assert deploy._routes({"routes": [{"custom_domain": "b.example"}]}) == ("b.example",)
    assert deploy._routes({}) == ()
    assert deploy._routes({"routes": [{"zone_name": "z"}]}) == ()


def _fixture_repo(root: Path, *, wrangler: str, baseline: dict[str, dict[str, str]]) -> None:
    """A minimal repo with one surface and a chosen production census."""
    app = root / "apps/w"
    app.mkdir(parents=True)
    (app / "wrangler.toml").write_text(wrangler, encoding="utf-8")
    (root / "config/contract").mkdir(parents=True)
    (root / "config/contract/services.yaml").write_text(
        "workers:\n  - name: w\n    file: apps/w/wrangler.toml\n", encoding="utf-8"
    )
    (root / "config/self-host").mkdir(parents=True)
    (root / "config/self-host/parity-baseline.json").write_text(
        json.dumps({"surface": {"wrangler": baseline}}), encoding="utf-8"
    )


# --------------------------------------------------------------------------
# Output: the same object renders as text or JSON
# --------------------------------------------------------------------------


def test_parity_table_states_that_unknown_is_not_a_pass() -> None:
    text = deploy.render_parity_table(
        [deploy.ParityRow("w", "routes", deploy.UNKNOWN, "nothing here")]
    )
    assert "UNKNOWN" in text
    assert "not a pass" in text


def test_binding_table_never_prints_a_value(tmp_path: Path) -> None:
    _fixture_repo(
        tmp_path, wrangler='name = "w"\nmain = "s.ts"\n[vars]\nSECRETISH = "value"\n', baseline={}
    )
    surface = deploy.load_surfaces(tmp_path)[0]
    table = deploy.render_binding_table(surface)
    assert "SECRETISH" in table
    assert "placeholder" in table


def test_binding_table_reports_an_absent_route_list(tmp_path: Path) -> None:
    """Absence of `[[routes]]` is a measurement and must be rendered as one."""
    _fixture_repo(tmp_path, wrangler='name = "w"\nmain = "s.ts"\n', baseline={})
    table = deploy.render_binding_table(deploy.load_surfaces(tmp_path)[0])
    assert "routes:" in table
    assert "none declared" in table


def test_deploy_module_is_importable_from_a_file_spec() -> None:
    """`scripts/dt` imports it as a package module; the file must load alone."""
    path = REPO / "scripts/localstack/deploy.py"
    loader = importlib.machinery.SourceFileLoader("deploy_check", str(path))
    spec = importlib.util.spec_from_loader("deploy_check", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolves sys.modules[cls.__module__].__dict__ for KW_ONLY
    # detection, so a module executed without being registered first raises
    # inside the @dataclass decorator - a harness artefact that reads exactly
    # like a defect in the file under test.
    sys.modules["deploy_check"] = module
    loader.exec_module(module)
    assert module.TARGET_ENVS == ("dev", "production")
    assert hasattr(contracts, "load_checks"), "the sibling modules are unchanged"


# --------------------------------------------------------------------------
# The CLI surface
# --------------------------------------------------------------------------


def _dt(*argv: str) -> int:
    """Run `scripts/dt` in-process so the exit code is the real one."""
    loader = importlib.machinery.SourceFileLoader("dt_cli", str(REPO / "scripts/dt"))
    spec = importlib.util.spec_from_loader("dt_cli", loader)
    assert spec is not None
    module = importlib.util.module_from_spec(spec)
    loader.exec_module(module)
    return module.main(list(argv))


def test_cli_lists_the_surfaces(capsys: pytest.CaptureFixture[str]) -> None:
    assert _dt("deploy", "--list") == 0
    out = capsys.readouterr().out
    assert "digithings-stack" in out
    assert "pages" in out


def test_cli_refuses_a_real_deploy_with_exit_two(capsys) -> None:
    assert _dt("deploy", "digithings-stack", "--env", "production") == 2
    assert "refusing" in capsys.readouterr().err


def test_cli_rejects_an_unknown_surface(capsys) -> None:
    assert _dt("deploy", "not-a-surface", "--dry-run") == 2
    assert "unknown surface" in capsys.readouterr().err


def test_cli_parity_is_json_when_asked(capsys) -> None:
    assert _dt("doctor", "parity", "--json") == 0
    payload = json.loads(capsys.readouterr().out)
    assert payload["verdict"] in {deploy.MATCH, "PARTIAL", deploy.DIFFERS}
    assert payload["counts"]["total"] > 0


def test_cli_parity_require_all_fails_on_an_unknown(
    capsys: pytest.CaptureFixture[str],
) -> None:
    """`--require-all` is how CI demands zero unknowns, as `dt status` does."""
    assert _dt("doctor", "parity", "--json") == 0
    capsys.readouterr()
    assert _dt("doctor", "parity", "--require-all") == 1


def test_existing_subcommands_still_parse() -> None:
    """Adding subcommands must not break the ones `dt up` already relies on."""
    assert _dt("preflight") in (0, 1)
    assert _dt("urls") == 0
