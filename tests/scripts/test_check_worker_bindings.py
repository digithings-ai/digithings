"""Mutants for scripts/check_worker_bindings.py, and the lanes that must run it.

WHAT THIS PINS. The first `digitrace-ingest` deploy (run 40525849901, DIG-5840)
spent the production approval, the install and the bundle, then failed inside
the Cloudflare API on a KV namespace id of 32 zeros. `wrangler deploy --dry-run`
could not catch it, because a dry run never asks the account whether a namespace
exists -- it only bundles.

So the check has one job: refuse an id that provably cannot exist, before the
lane reaches the API. The tests below are the two ways that job can go wrong:

* too weak -- an all-zero id, a UUID of zeros, or an unresolved `<...>` slot
  passes and the lane burns an approval again;
* too strong -- a *documented local-only* stand-in such as digidata-api's
  ``00000000-0000-0000-0000-00000000d1a1`` is flagged, which would block a lane
  that would have worked. The rule is "this id cannot exist in any account",
  not "this id looks unfamiliar", and one test holds that line.

The last tests read the real deploy lanes: a check nobody calls is prose.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import ModuleType

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_worker_bindings.py"

#: Lanes that deploy a Worker from `apps/<app>/wrangler.toml` and must run the
#: preflight, with the line that performs the deploy. A new Worker lane joins
#: this list when it joins the check.
WIRED_LANES: dict[str, tuple[str, str]] = {
    ".github/workflows/deploy-digitrace-ingest.yml": (
        "apps/digitrace-ingest/wrangler.toml",
        "uses: cloudflare/wrangler-action@v3",
    ),
    ".github/workflows/deploy-digiquant-runner.yml": (
        "apps/digiquant-runner/wrangler.toml",
        "run: npx wrangler deploy -c apps/digiquant-runner/wrangler.toml",
    ),
    ".github/workflows/deploy-digithings-cron.yml": (
        "apps/digithings-cron/wrangler.toml",
        "uses: cloudflare/wrangler-action@v3",
    ),
}

ZERO_KV = "0" * 32
REAL_KV = "16160cf4a1b2c3d4e5f60718293a4b5c"
ZERO_UUID = "00000000-0000-0000-0000-000000000000"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("check_worker_bindings", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    # `Finding` is a dataclass, and the decorator resolves the module's
    # namespace through `sys.modules`. Without this line the check's own
    # import target is not registered, so the first `Finding` raises
    # `AttributeError: 'NoneType' object has no attribute '__dict__'` and every
    # rule test errors at fixture setup instead of testing a rule.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


@pytest.fixture(scope="module")
def check() -> ModuleType:
    return _load()


def _config(kv_id: str, binding: str = "INGEST_TOKENS") -> str:
    return (
        f'name = "demo"\n'
        f"\n"
        f"[[kv_namespaces]]\n"
        f'binding = "{binding}"\n'
        f'id = "{kv_id}"\n'
    )


def _write(tmp_path: Path, text: str, app: str = "demo") -> Path:
    path = tmp_path / "apps" / app / "wrangler.toml"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


# --------------------------------------------------------------------------- #
# The rule itself
# --------------------------------------------------------------------------- #


def test_all_zero_kv_id_is_refused_with_binding_and_line(check: ModuleType) -> None:
    findings = check.scan_text(_config(ZERO_KV), "apps/demo/wrangler.toml")

    assert len(findings) == 1
    assert findings[0].binding == "INGEST_TOKENS"
    assert findings[0].key == "id"
    assert findings[0].line == 5
    assert findings[0].value == ZERO_KV
    # The hint has to be actionable: the command that mints a real id.
    assert "wrangler kv namespace create" in findings[0].hint


def test_real_kv_id_is_clean(check: ModuleType) -> None:
    assert check.scan_text(_config(REAL_KV), "apps/demo/wrangler.toml") == []


@pytest.mark.parametrize("value", ["REPLACE_ME", "changeme", "TODO", "<your-kv-id>"])
def test_unresolved_templates_are_refused(check: ModuleType, value: str) -> None:
    assert check.scan_text(_config(value), "apps/demo/wrangler.toml")


def test_empty_id_is_refused(check: ModuleType) -> None:
    assert check.scan_text(_config(""), "apps/demo/wrangler.toml")


def test_all_zero_d1_database_id_is_refused(check: ModuleType) -> None:
    text = (
        'name = "demo"\n'
        "\n"
        "[[d1_databases]]\n"
        'binding = "DEMO_DB"\n'
        'database_name = "demo"\n'
        f'database_id = "{ZERO_UUID}"\n'
    )

    findings = check.scan_text(text, "apps/demo/wrangler.toml")

    assert [f.binding for f in findings] == ["DEMO_DB"]
    assert "wrangler d1 create" in findings[0].hint


def test_documented_local_only_stand_in_is_not_refused(check: ModuleType) -> None:
    """digidata-api's local D1 id is not all zeros, and must stay deployable.

    `apps/digidata-api/wrangler.toml` documents this value as a local-only
    stand-in for `wrangler dev`. It is a real remote database only at cutover.
    A check that flags it would teach the next person to disable the check.
    """
    text = (
        'name = "demo"\n'
        "\n"
        "[[d1_databases]]\n"
        'binding = "TWELVEX_DB"\n'
        'database_name = "twelvex"\n'
        'database_id = "00000000-0000-0000-0000-00000000d1a1"\n'
    )

    assert check.scan_text(text, "apps/demo/wrangler.toml") == []


def test_env_scoped_binding_table_is_checked(check: ModuleType) -> None:
    """A staging/production override table is the same binding, same rule."""
    text = (
        'name = "demo"\n'
        "\n"
        "[[env.production.kv_namespaces]]\n"
        'binding = "INGEST_TOKENS"\n'
        f'id = "{ZERO_KV}"\n'
    )

    findings = check.scan_text(text, "apps/demo/wrangler.toml")

    assert [f.binding for f in findings] == ["INGEST_TOKENS"]


def test_an_id_outside_a_binding_table_is_ignored(check: ModuleType) -> None:
    """Only the binding tables are ours. A `[vars]` entry named `id` is not."""
    text = (
        'name = "demo"\n'
        "\n"
        "[vars]\n"
        f'id = "{ZERO_KV}"\n'
    )

    assert check.scan_text(text, "apps/demo/wrangler.toml") == []


# --------------------------------------------------------------------------- #
# The command
# --------------------------------------------------------------------------- #


def test_main_is_clean_on_a_real_id(check: ModuleType, tmp_path: Path) -> None:
    _write(tmp_path, _config(REAL_KV))

    assert check.main(["--root", str(tmp_path), "--config", "apps/demo/wrangler.toml"]) == 0


def test_main_refuses_a_placeholder_and_names_the_file(
    check: ModuleType, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _write(tmp_path, _config(ZERO_KV))

    assert check.main(["--root", str(tmp_path), "--config", "apps/demo/wrangler.toml"]) == 1
    out = capsys.readouterr().out
    assert "apps/demo/wrangler.toml:5" in out
    assert "INGEST_TOKENS" in out


def test_missing_config_is_a_usage_error_not_a_pass(check: ModuleType, tmp_path: Path) -> None:
    """A typo in the lane must not read as "clean"."""
    assert check.main(["--root", str(tmp_path), "--config", "apps/gone/wrangler.toml"]) == 2


def test_all_mode_scans_every_app(check: ModuleType, tmp_path: Path) -> None:
    _write(tmp_path, _config(REAL_KV, "A"), app="one")
    _write(tmp_path, _config(ZERO_KV, "B"), app="two")

    assert check.main(["--root", str(tmp_path), "--all"]) == 1


# --------------------------------------------------------------------------- #
# The lanes
# --------------------------------------------------------------------------- #


@pytest.mark.parametrize(
    ("lane", "config", "deploy"),
    sorted((k, config, deploy) for k, (config, deploy) in WIRED_LANES.items()),
)
def test_lane_runs_the_preflight_before_it_deploys(lane: str, config: str, deploy: str) -> None:
    text = (REPO_ROOT / lane).read_text(encoding="utf-8")
    invocation = f"scripts/check_worker_bindings.py --config {config}"

    assert invocation in text, f"{lane} does not run the placeholder preflight"
    # Ordering is the point: a preflight after the deploy step checks nothing.
    assert text.index(invocation) < text.rindex(deploy), (
        f"{lane} runs the preflight after the deploy step"
    )
