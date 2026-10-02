"""Install, update, and uninstall — CLI + Hammerspoon + models, with SHA guard.

No test downloads weights, rsyncs Application Support, or needs a Mac.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digivoice.cli import Runtime, run
from digivoice.errors import AdapterGuardError
from digivoice.install import (
    DEFAULT_STT_MODEL_URL,
    TIP_STAMP,
    app_support_hammerspoon,
    guard_adapter_sync,
    run_install,
    run_uninstall,
    user_adapter_dir,
)
from digivoice.paths import DEFAULT_MODEL_FILE, resolve_paths

from tests.dvo.fakes import FakeCall, FakeProbe, FakeReply, FakeRunner

pytestmark = pytest.mark.unit

TIP = "99fdde3c7c2513de4bbf60bc784ff536d398c6a9"
OTHER = "aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"


def _runtime(tmp_path: Path, **env: str) -> Runtime:
    merged = {"DIGIVOICE_DATA_DIR": str(tmp_path), "PATH": "/usr/bin", **env}
    return Runtime(platform="linux", home=tmp_path, env=merged, probe=FakeProbe())


def _source(tmp_path: Path) -> Path:
    source = tmp_path / "checkout" / "digivoice" / "hammerspoon"
    source.mkdir(parents=True)
    (source / "init.lua").write_text("-- adapter\n", encoding="utf-8")
    (source / "banner_core.lua").write_text("-- core\n", encoding="utf-8")
    return source


def test_guard_refuses_app_support_copy_without_matching_tip(tmp_path: Path) -> None:
    dest = app_support_hammerspoon(tmp_path)
    dest.mkdir(parents=True)
    (dest / "init.lua").write_text("-- live banner tip\n", encoding="utf-8")
    (dest / TIP_STAMP).write_text(OTHER + "\n", encoding="utf-8")
    with pytest.raises(AdapterGuardError, match="refusing to overwrite"):
        guard_adapter_sync(dest=dest, source_sha=TIP)


def test_guard_refuses_app_support_copy_with_missing_stamp(tmp_path: Path) -> None:
    dest = app_support_hammerspoon(tmp_path)
    dest.mkdir(parents=True)
    (dest / "init.lua").write_text("-- unknown live adapter\n", encoding="utf-8")
    with pytest.raises(AdapterGuardError, match="stamp=missing"):
        guard_adapter_sync(dest=dest, source_sha=TIP)


def test_guard_allows_matching_tip_sha(tmp_path: Path) -> None:
    dest = app_support_hammerspoon(tmp_path)
    dest.mkdir(parents=True)
    (dest / "init.lua").write_text("-- same tip\n", encoding="utf-8")
    (dest / TIP_STAMP).write_text(TIP + "\n", encoding="utf-8")
    guard_adapter_sync(dest=dest, source_sha=TIP)


def test_install_symlinks_user_adapter_and_never_copies_app_support(tmp_path: Path) -> None:
    source = _source(tmp_path)
    app_support = app_support_hammerspoon(tmp_path)
    result = run_install(
        "darwin",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path / "data")},
        source_dir=source,
        tip_sha=TIP,
    )
    assert result.code == 0
    adapter = user_adapter_dir(tmp_path)
    assert adapter.is_symlink()
    assert adapter.resolve() == source.resolve()
    assert (adapter / "init.lua").is_file()
    assert not app_support.exists()
    assert "Application Support" not in result.stdout or "left alone" in result.stdout
    assert "symlink" in result.stdout


def test_install_bootstraps_models_dir_without_downloading(tmp_path: Path) -> None:
    source = _source(tmp_path)
    data = tmp_path / "data"
    runner = FakeRunner({"curl": FakeReply(code=99, stderr="should not run")})
    result = run_install(
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(data)},
        source_dir=source,
        tip_sha=TIP,
        runner=runner,
    )
    assert result.code == 0
    paths = resolve_paths("linux", tmp_path, {"DIGIVOICE_DATA_DIR": str(data)})
    assert Path(paths.models_dir).is_dir()
    assert Path(paths.recordings_dir).is_dir()
    assert not (Path(paths.models_dir) / DEFAULT_MODEL_FILE).exists()
    assert "curl" not in runner.programs
    stamp = json.loads((Path(paths.data_dir) / "install.json").read_text(encoding="utf-8"))
    assert stamp["tip_sha"] == TIP
    assert stamp["adapter_source"] == str(source.resolve())


def test_install_fetch_models_uses_injected_runner(tmp_path: Path) -> None:
    source = _source(tmp_path)
    data = tmp_path / "data"

    def curl(call: FakeCall) -> FakeReply:
        dest = Path(call.argv[call.argv.index("-o") + 1])
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(b"fake ggml")
        assert call.argv[-1] == DEFAULT_STT_MODEL_URL
        return FakeReply(code=0)

    runner = FakeRunner({"curl": curl})
    result = run_install(
        "linux",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(data)},
        source_dir=source,
        tip_sha=TIP,
        fetch_models=True,
        runner=runner,
    )
    assert result.code == 0
    model = data / "models" / DEFAULT_MODEL_FILE
    assert model.read_bytes() == b"fake ggml"
    assert "curl" in runner.programs


def test_install_leaves_mismatched_app_support_copy_in_place(tmp_path: Path) -> None:
    source = _source(tmp_path)
    dest = app_support_hammerspoon(tmp_path)
    dest.mkdir(parents=True)
    (dest / "init.lua").write_text("-- banner tip from #4965\n", encoding="utf-8")
    (dest / "banner_core.lua").write_text("-- hover chrome\n", encoding="utf-8")
    (dest / TIP_STAMP).write_text(OTHER + "\n", encoding="utf-8")
    result = run_install(
        "darwin",
        tmp_path,
        {"DIGIVOICE_DATA_DIR": str(tmp_path / "data")},
        source_dir=source,
        tip_sha=TIP,
        replace_app_support_adapter=True,
    )
    assert result.code == 1
    assert "refusing" in result.stdout
    assert (dest / "init.lua").read_text(encoding="utf-8") == "-- banner tip from #4965\n"
    assert user_adapter_dir(tmp_path).is_symlink()


def test_uninstall_removes_symlink_and_keeps_data(tmp_path: Path) -> None:
    source = _source(tmp_path)
    data = tmp_path / "data"
    env = {"DIGIVOICE_DATA_DIR": str(data)}
    installed = run_install("linux", tmp_path, env, source_dir=source, tip_sha=TIP)
    assert installed.code == 0
    (data / "models" / DEFAULT_MODEL_FILE).parent.mkdir(parents=True, exist_ok=True)
    (data / "models" / DEFAULT_MODEL_FILE).write_bytes(b"keep")
    result = run_uninstall("linux", tmp_path, env)
    assert result.code == 0
    assert not user_adapter_dir(tmp_path).exists()
    assert (data / "models" / DEFAULT_MODEL_FILE).read_bytes() == b"keep"
    assert (data / "install.json").exists() is False or "removed" in result.stdout


def test_uninstall_purge_data_removes_data_dir(tmp_path: Path) -> None:
    source = _source(tmp_path)
    data = tmp_path / "data"
    env = {"DIGIVOICE_DATA_DIR": str(data)}
    run_install("linux", tmp_path, env, source_dir=source, tip_sha=TIP)
    (data / "history.jsonl").write_text("{}\n", encoding="utf-8")
    result = run_uninstall("linux", tmp_path, env, purge_data=True)
    assert result.code == 0
    assert not data.exists()


def test_cli_update_and_install_are_wired(tmp_path: Path) -> None:
    source = _source(tmp_path)
    runtime = _runtime(
        tmp_path,
        DIGIVOICE_HAMMERSPOON_SOURCE=str(source),
        DIGIVOICE_TIP_SHA=TIP,
    )
    update = run(["update"], runtime)
    assert update.code == 0
    assert "not wired yet" not in update.stdout
    assert "symlink" in update.stdout
    again = run(["install"], runtime)
    assert again.code == 0
    uninstall = run(["uninstall"], runtime)
    assert uninstall.code == 0
    assert "not wired yet" not in uninstall.stdout


def test_install_script_forbids_app_support_rsync() -> None:
    script = Path(__file__).resolve().parents[2] / "digivoice" / "scripts" / "install.sh"
    text = script.read_text(encoding="utf-8")
    assert "rev-parse" in text
    assert "rsync" in text
    assert "Application Support" in text
    assert "digivoice install" in text or "python -m digivoice install" in text
    # The script must mention the SHA guard, not perform an unguarded copy.
    assert "DIGIVOICE_TIP_SHA" in text or "tip" in text.lower()


def test_install_script_prefers_uv_tool_without_bare_uv_pip() -> None:
    script = Path(__file__).resolve().parents[2] / "digivoice" / "scripts" / "install.sh"
    text = script.read_text(encoding="utf-8")
    assert "uv tool install -e" in text
    tool_pos = text.index("uv tool install -e")
    pip_pos = text.index("uv pip install -e")
    assert tool_pos < pip_pos, "uv tool install must run before uv pip fallback"
    assert "VIRTUAL_ENV" in text or ".venv" in text
    assert "rsync" in text
