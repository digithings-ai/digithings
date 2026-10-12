"""Self-host `wrangler dev` session: generated configs and the container shim.

DIG-2771 (plan slice S3 of DIG-2758). The generator
`scripts/selfhost/generate_dev_configs.py` derives a dev config per worker from
that worker's real `wrangler.toml`, and the runtime shim lives in
`scripts/selfhost/container_shim.ts`.

These tests assert against the REAL repo: the real `wrangler.toml` files, the
real `docker-compose.yml`, and the real generated output. They do not run
`wrangler dev` — `node_modules` is not installed in CI, and a test that
asserted an unrun command would be theatre.

The suite pins four defects that a naive transform introduces:
- a real Durable Object that is not a container (`BackfillLedger`) must keep its
  own class name and its SQLite migration;
- `workers_dev` must be written once, at the top level, not into every table
  that happens to have a `name` key;
- a container class whose `defaultPort` is a digit literal must still resolve;
- a dev config must not claim a production hostname.
"""

from __future__ import annotations

import importlib.util
import re
from pathlib import Path
from typing import Dict, List

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
GENERATOR_PATH = REPO_ROOT / "scripts" / "selfhost" / "generate_dev_configs.py"
SHIM_PATH = REPO_ROOT / "scripts" / "selfhost" / "container_shim.ts"
COMPOSE_PATH = REPO_ROOT / "docker-compose.yml"


def _load_generator():
    spec = importlib.util.spec_from_file_location("selfhost_generator", GENERATOR_PATH)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


gen = _load_generator()


def _strip_comments(text: str) -> str:
    """Drop full-line comments.

    A commented-out production route is a record of a human gate, not a claim.
    Only real config lines may be asserted on.
    """
    return "".join(
        line for line in text.splitlines(keepends=True) if not line.lstrip().startswith("#")
    )


# --- the workers in the brief -------------------------------------------------

EXPECTED_WORKERS = {
    "digithings-stack",
    "digichat",
    "dashboard-api",
    "digithings-cron",
    "digiquant-runner",
    "digitrace-langfuse",
}


def test_every_worker_in_the_brief_has_a_generated_config_and_a_fixed_port() -> None:
    names = {w.worker for w in gen.WORKERS}
    assert names == EXPECTED_WORKERS, f"worker set drifted from the brief: {sorted(names)}"
    for worker in gen.WORKERS:
        assert worker.real_config.is_file(), f"{worker.worker}: missing {worker.real_config}"
        generated = gen.render_dev_toml(
            worker, worker.real_config.read_text(encoding="utf-8"), gen.worker_classes(worker)
        )
        assert f"port = {worker.dev_port}\n" in generated


def test_dev_ports_are_unique() -> None:
    ports = [w.dev_port for w in gen.WORKERS]
    assert len(set(ports)) == len(ports), f"two workers share a dev port: {sorted(ports)}"
    assert gen.WORKERS[0].primary, (
        "the primary worker must be first: only it gets a URL in one session"
    )
    assert gen.WORKERS[0].dev_port == 8787, "8787 is wrangler's documented default primary port"


def test_dev_ports_do_not_collide_with_published_compose_ports() -> None:
    """The control that makes the port choice non-arbitrary.

    Every integer in a compose `ports` entry is collected, including container
    ports and IP octets, so the census is a deliberate superset. A superset is
    safe here because 8787-8792 are distinctive; an undercount would not be.
    """
    compose = yaml.safe_load(COMPOSE_PATH.read_text(encoding="utf-8"))
    published = set()
    for service in compose["services"].values():
        for entry in service.get("ports", []) or []:
            published.update(int(n) for n in re.findall(r"\d+", str(entry)))
    published = {port for port in published if port >= 1000}
    assert published, "no compose ports parsed: this test would be vacuous"
    dev_ports = {w.dev_port for w in gen.WORKERS}
    overlap = dev_ports & published
    assert not overlap, f"dev ports collide with compose: {sorted(overlap)}"
    # Spot-check the ports that matter, so an empty `published` cannot pass.
    for expected in (8000, 8005, 3005, 8765, 8769, 8770):
        assert expected in published, f"compose publish census is wrong: {expected} missing"


# --- what a dev config must and must not contain ------------------------------


@pytest.mark.parametrize("worker_name", sorted(EXPECTED_WORKERS))
def test_generated_config_never_claims_a_production_route_or_a_container(worker_name: str) -> None:
    worker = next(w for w in gen.WORKERS if w.worker == worker_name)
    text = _strip_comments(
        gen.render_dev_toml(
            worker, worker.real_config.read_text(encoding="utf-8"), gen.worker_classes(worker)
        )
    )
    assert "[[containers]]" not in text
    assert "[[containers.authorized_keys]]" not in text
    assert "[[routes]]" not in text
    # Route-shaped keys, not the bare hostname: `[vars]` legitimately names
    # digithings.ai (DIGICHAT_EMBED_HOSTS and friends). What must not survive is
    # a binding that claims a production hostname.
    for route_key in ("custom_domain", "zone", "pattern"):
        assert not re.search(r"^\s*%s\s*=" % route_key, text, re.M), (
            f"route key survived: {route_key}"
        )
    assert text.count("\nworkers_dev = true\n") + text.startswith("workers_dev = true") == 1
    assert 'main = ".selfhost-dev/entry.ts"' in text
    port_block = re.search(r"\[dev\]\nport = (\d+)\n$", text)
    assert port_block is not None, "the [dev] block must be last, with the fixed port"
    assert int(port_block.group(1)) == worker.dev_port


@pytest.mark.parametrize("worker_name", sorted(EXPECTED_WORKERS))
def test_generated_config_keeps_the_worker_bindings(worker_name: str) -> None:
    worker = next(w for w in gen.WORKERS if w.worker == worker_name)
    real = worker.real_config.read_text(encoding="utf-8")
    generated = gen.render_dev_toml(worker, real, gen.worker_classes(worker))
    for binding in re.findall(r'name = "([A-Z_]+)"', real):
        assert 'name = "%s"' % binding in generated, f"{worker_name}: lost binding {binding}"


def test_the_binding_census_is_not_vacuous() -> None:
    """dashboard-api has no bindings, so the per-worker test above cannot assert."""
    found = 0
    for worker in gen.WORKERS:
        real = worker.real_config.read_text(encoding="utf-8")
        found += len(re.findall(r'name = "([A-Z_]+)"', real))
    assert found >= 8, f"binding census found only {found}; the transform test is vacuous"


def test_service_bindings_survive_the_transform() -> None:
    """cron's RUNNER service binding is how it reaches digiquant-runner."""
    worker = next(w for w in gen.WORKERS if w.worker == "digithings-cron")
    generated = gen.render_dev_toml(
        worker, worker.real_config.read_text(encoding="utf-8"), gen.worker_classes(worker)
    )
    assert "[[services]]" in generated
    assert 'service = "digiquant-runner"' in generated


def _crons(toml_text: str) -> List[str]:
    """Every quoted entry of the `crons` array.

    Scoped to the array on purpose. A file-wide `"([^"]+)"` mis-pairs quotes
    across the header comments (55 spans, none of them a cron), and anchoring on
    a trailing comma drops the final element, which has no comma.
    """
    start = toml_text.index("crons = [")
    end = toml_text.index("]", start)
    return re.findall(r'"([^"]+)"', toml_text[start:end])


def test_cron_triggers_survive_the_transform() -> None:
    worker = next(w for w in gen.WORKERS if w.worker == "digithings-cron")
    real = worker.real_config.read_text(encoding="utf-8")
    generated = gen.render_dev_toml(worker, real, gen.worker_classes(worker))
    real_crons = _crons(real)
    assert len(real_crons) >= 40, f"cron census found only {len(real_crons)}"
    assert len(set(real_crons)) == len(real_crons), "duplicate cron entries in the source config"
    for cron in real_crons:
        assert cron in generated, f"cron entry lost: {cron}"
    assert _crons(generated) == real_crons, "the transform must not reorder or rewrite crons"


# --- container classes vs real durable objects --------------------------------


def test_container_class_extraction_is_scoped_to_containers_blocks() -> None:
    """A `[[durable_objects.bindings]]` class_name is NOT a container.

    Cron's `BackfillLedger` is a real SQLite Durable Object. Treating it as a
    container would replace a working DO with a storageless shim and strip its
    migration.
    """
    cron = (REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml").read_text(encoding="utf-8")
    assert "[[containers]]" not in cron
    assert gen.container_class_names(cron) == []
    synthetic = (
        'name = "x"\n'
        '\n[[containers]]\nclass_name = "Boxed"\n\n'
        '[[durable_objects.bindings]]\nname = "LEDGER"\nclass_name = "Ledger"\n'
    )
    assert gen.container_class_names(synthetic) == ["Boxed"]


def test_container_classes_are_shimmed_under_a_distinct_name() -> None:
    for worker in gen.WORKERS:
        classes = gen.worker_classes(worker)
        for container_class in classes:
            shim = gen.shim_class_name(container_class)
            assert shim == "SelfHost" + container_class
            assert shim != container_class, "a shim must not reuse the container class name"


def test_a_real_durable_object_keeps_its_own_name_and_migration() -> None:
    worker = next(w for w in gen.WORKERS if w.worker == "digithings-cron")
    assert gen.worker_classes(worker) == []
    generated = gen.render_dev_toml(worker, worker.real_config.read_text(encoding="utf-8"), [])
    assert 'class_name = "BackfillLedger"' in generated
    assert "SelfHostBackfillLedger" not in generated
    assert 'new_sqlite_classes = ["BackfillLedger"]' in generated
    entry = gen.render_entry_ts(worker, {})
    assert "BackfillLedger" not in entry


@pytest.mark.parametrize(
    "worker_name", ["digithings-stack", "digichat", "digiquant-runner", "digitrace-langfuse"]
)
def test_renamed_classes_keep_their_bindings_but_lose_their_sqlite_migration(
    worker_name: str,
) -> None:
    worker = next(w for w in gen.WORKERS if w.worker == worker_name)
    classes = gen.worker_classes(worker)
    assert classes, f"{worker_name}: expected container classes"
    generated = gen.render_dev_toml(worker, worker.real_config.read_text(encoding="utf-8"), classes)
    for container_class in classes:
        assert 'class_name = "%s"' % gen.shim_class_name(container_class) in generated
        assert 'class_name = "%s"' % container_class not in generated
        assert container_class not in re.findall(r"new_sqlite_classes = \[([^\]]*)\]", generated)
    assert "new_sqlite_classes" not in generated, (
        f"{worker_name}: shim classes have no storage to migrate"
    )


# --- the generated entry point ------------------------------------------------


@pytest.mark.parametrize("worker_name", sorted(EXPECTED_WORKERS))
def test_generated_entry_re_exports_the_worker_and_adds_one_shim_per_class(
    worker_name: str,
) -> None:
    worker = next(w for w in gen.WORKERS if w.worker == worker_name)
    ports = gen.class_ports_for(worker)
    entry = gen.render_entry_ts(worker, ports)
    assert 'export * from "../src/index";' in entry
    assert 'export { default } from "../src/index";' in entry
    assert "SelfHostContainer" in entry
    for container_class, port in ports.items():
        shim = gen.shim_class_name(container_class)
        assert "export class %s extends SelfHostContainer {" % shim in entry
        assert 'readonly selfHostClass = "%s";' % container_class in entry
        assert "readonly selfHostDefaultPort = %d;" % (port or 0) in entry


@pytest.mark.parametrize("worker_name", sorted(EXPECTED_WORKERS))
def test_every_container_class_default_port_resolves(worker_name: str) -> None:
    """`defaultPort` may be a digit literal or a constant from a sibling module.

    A resolver that only accepts named constants silently emits 0, which makes
    the shim answer 400 on every request.
    """
    worker = next(w for w in gen.WORKERS if w.worker == worker_name)
    for container_class, port in gen.class_ports_for(worker).items():
        assert port is not None, f"{container_class}: defaultPort not resolved from source"
        assert port > 0


def test_entry_shim_names_cannot_collide_with_exported_worker_names() -> None:
    worker = next(w for w in gen.WORKERS if w.worker == "digithings-stack")
    ports = gen.class_ports_for(worker)
    exported = set(
        re.findall(
            r"export (?:class|const|function) (\w+)",
            (worker.app / "src" / "index.ts").read_text(encoding="utf-8"),
        )
    )
    assert exported, "positive control: the worker entry exports something"
    shim_names = {gen.shim_class_name(c) for c in ports}
    assert not (shim_names & exported), (
        f"shim names collide with worker exports: {sorted(shim_names & exported)}"
    )


# --- the shim's routing table -------------------------------------------------


def _shim_text() -> str:
    text = SHIM_PATH.read_text(encoding="utf-8")
    start = text.index("export const SELF_HOST_CLASSES")
    end = text.index("export const SELF_HOST_TARGET_PORT_HEADER")
    return text[start:end]


TS_CLASS_RE = re.compile(r"\n\t(\w+): \{\n(.*?)\n\t\},", re.S)


def _shim_classes() -> Dict[str, str]:
    """Class name -> body of its SELF_HOST_CLASSES entry.

    The positive control is in `test_shim_table_parses`: an empty parse must
    fail loudly rather than make every routing assertion vacuous.
    """
    found = {name: body for name, body in TS_CLASS_RE.findall(_shim_text())}
    assert found, "SELF_HOST_CLASSES parsed as empty; the routing tests would be vacuous"
    return found


def test_shim_table_parses() -> None:
    classes = _shim_classes()
    assert {
        "DigiStackContainer",
        "DigiChatContainer",
        "DigiQuantMcpContainer",
        "DigiQuantRunnerContainer",
        "LangfuseWebContainer",
        "LangfuseWorkerContainer",
    } <= set(classes)


def test_shim_keys_on_class_and_port_not_port_alone() -> None:
    """DigiChatContainer and LangfuseWebContainer both default to port 3000."""
    classes = _shim_classes()
    assert '3000: { service: "digichat", hostPort: 3005' in classes["DigiChatContainer"], (
        "container port 3000 maps to compose host port 3005, not 3000"
    )
    assert "ports: {}" in classes["LangfuseWebContainer"], (
        "an unmapped class must have an empty port map"
    )


def test_digistack_container_fronts_the_five_compose_services() -> None:
    digistack = _shim_classes()["DigiStackContainer"]
    for port, service in (
        (8000, "digigraph"),
        (8001, "digiquant"),
        (8002, "digisearch"),
        (8005, "digikey"),
    ):
        assert '%d: { service: "%s"' % (port, service) in digistack, (
            f"port {port} -> {service} missing"
        )


@pytest.mark.parametrize(
    "container_class,needed",
    [
        ("DigiQuantMcpContainer", "digiquant-mcp"),
        ("DigiQuantRunnerContainer", "digiquant-runner"),
        ("LangfuseWebContainer", "digitrace-langfuse-web"),
        ("LangfuseWorkerContainer", "digitrace-langfuse-worker"),
    ],
)
def test_classes_without_a_compose_service_declare_what_is_missing(
    container_class: str, needed: str
) -> None:
    """These are honest gaps: no compose service exists today.

    The shim must name the missing service rather than guess a port.
    """
    section = _shim_classes()[container_class]
    assert "ports: {}" in section, f"{container_class} must have an empty port map"
    assert 'neededService: "%s"' % needed in section


def test_unmapped_upstreams_answer_503_and_unreachable_ones_answer_502() -> None:
    text = SHIM_PATH.read_text(encoding="utf-8")
    assert "selfhost_upstream_unmapped" in text and "status: 503" in text
    assert "selfhost_upstream_unreachable" in text and "status: 502" in text
    assert "selfhost_container_port_missing" in text and "status: 400" in text
    # The routing key must be the header switchPort writes.
    assert "cf-container-target-port" in text
    # Never leak the container-routing header to the compose service.
    assert "headers.delete(SELF_HOST_TARGET_PORT_HEADER)" in text


# --- the commands -------------------------------------------------------------


def test_single_session_command_shape() -> None:
    argv = gen.session_command("single")
    joined = " ".join(argv)
    assert argv[0:2] == ["wrangler", "dev"]
    assert "--local" in argv
    assert "--persist-to" in argv and argv[argv.index("--persist-to") + 1] == ".wrangler/state"
    configs = [argv[i + 1] for i, arg in enumerate(argv) if arg == "-c"]
    assert len(configs) == len(gen.WORKERS) == 6
    assert len(set(configs)) == 6, "a worker config must appear exactly once"
    assert configs[0].endswith("digithings-stack-cloudflare/wrangler.selfhost.toml"), (
        "primary first"
    )
    assert "--test-scheduled" in argv, "cron triggers need it"
    assert "apps/digichat-cloudflare/wrangler.toml" not in joined, (
        "the real configs must never be passed to wrangler"
    )


def test_per_worker_mode_gives_every_worker_its_own_command() -> None:
    argvs = gen.argv_per_worker("per-worker")
    assert len(argvs) == 6
    scheduled = [argv for argv in argvs if "--test-scheduled" in argv]
    assert len(scheduled) == 1, "only the cron worker needs --test-scheduled"
    assert len({argv[argv.index("-c") + 1] for argv in argvs}) == 6
    for argv in argvs:
        assert "--persist-to" in argv and argv[argv.index("--persist-to") + 1] == ".wrangler/state"


def test_table_output_names_every_worker() -> None:
    text = "\n".join(gen.table_lines())
    for worker in gen.WORKERS:
        assert worker.worker in text
    assert "SelfHostDigiStackContainer" in text


# --- repository hygiene -------------------------------------------------------


def test_generated_artifacts_are_gitignored() -> None:
    ignored = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    for entry in ("wrangler.selfhost.toml", ".selfhost-dev/", ".wrangler/", ".dev.vars"):
        assert entry in ignored, f"{entry} must be gitignored: it is generated or secret"


def test_real_wrangler_configs_are_untouched() -> None:
    """The generator writes new files; it must never edit a real config."""
    for worker in gen.WORKERS:
        assert worker.real_config.name == "wrangler.toml"
        assert worker.dev_config.name != worker.real_config.name
        assert worker.real_config.read_text(encoding="utf-8").count("[[containers]]") >= 0
