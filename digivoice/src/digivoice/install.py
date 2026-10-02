"""Install, update, and uninstall for the local CLI + Hammerspoon adapter.

One-command from a checkout is `bash digivoice/scripts/install.sh`. Once the
CLI is importable, `digivoice install` / `update` is the same path: symlink the
Lua adapter into `~/.hammerspoon/digivoice`, create the data/models dirs, and
optionally fetch `ggml-base.en.bin`.

Never rsync or copy the adapter into
`~/Library/Application Support/digivoice/hammerspoon` without a matching
`.digivoice-tip` SHA — that overwrite wiped the #4965 banner tip.
"""

from __future__ import annotations

import json
import os
import shutil
from collections.abc import Mapping
from pathlib import Path

from digivoice.errors import AdapterGuardError
from digivoice.models import CliResult, InstallStamp
from digivoice.paths import DEFAULT_MODEL_FILE, resolve_paths
from digivoice.reload import ensure_digivoice_require, resolve_cli_path
from digivoice.runner import CommandRunner, run_command

TIP_STAMP = ".digivoice-tip"
INSTALL_STAMP = "install.json"
DEFAULT_STT_MODEL_URL = "https://huggingface.co/ggerganov/whisper.cpp/resolve/main/ggml-base.en.bin"


def package_root(package_file: str = __file__) -> Path:
    """`digivoice/` directory that holds `src/` and `hammerspoon/`."""
    return Path(package_file).resolve().parents[2]


def repo_root(package_file: str = __file__) -> Path:
    return package_root(package_file).parent


def default_source_dir(package_file: str = __file__) -> Path:
    return package_root(package_file) / "hammerspoon"


def user_adapter_dir(home: Path) -> Path:
    return home / ".hammerspoon" / "digivoice"


def app_support_hammerspoon(home: Path) -> Path:
    return home / "Library" / "Application Support" / "digivoice" / "hammerspoon"


def read_tip_stamp(adapter_dir: Path) -> str | None:
    stamp = adapter_dir / TIP_STAMP
    if not stamp.is_file():
        return None
    text = stamp.read_text(encoding="utf-8").strip().splitlines()
    return text[0].strip() if text else None


def guard_adapter_sync(*, dest: Path, source_sha: str) -> None:
    """Refuse overwriting a live adapter copy without a matching tip SHA.

    A checkout rsync from a TUI branch onto Application Support wiped the
    #4965 banner tip. Any dest that already has `init.lua` must carry
    `.digivoice-tip` equal to `source_sha` or this raises.
    """
    if not dest.exists():
        return
    if dest.is_symlink():
        return
    init = dest / "init.lua"
    if not init.is_file():
        return
    dest_sha = read_tip_stamp(dest)
    if dest_sha == source_sha:
        return
    shown = dest_sha or "missing"
    raise AdapterGuardError(
        f"refusing to overwrite {dest} (stamp={shown}) with source tip "
        f"{source_sha[:8]} — rsync/copy would wipe a live banner adapter. "
        "Use the ~/.hammerspoon/digivoice symlink instead."
    )


def _resolve_source(env: Mapping[str, str], source_dir: Path | None) -> Path:
    if source_dir is not None:
        return Path(source_dir)
    override = env.get("DIGIVOICE_HAMMERSPOON_SOURCE", "")
    if override:
        return Path(override)
    return default_source_dir()


def _resolve_tip_sha(
    env: Mapping[str, str],
    tip_sha: str | None,
    runner: CommandRunner,
    checkout: Path,
) -> str:
    if tip_sha:
        return tip_sha
    override = env.get("DIGIVOICE_TIP_SHA", "")
    if override:
        return override
    result = runner(["git", "-C", str(checkout), "rev-parse", "HEAD"], timeout=8.0)
    sha = (result.stdout or "").strip().splitlines()
    if result.code == 0 and sha:
        return sha[0].strip()
    return "unknown"


def _link_user_adapter(home: Path, source: Path, tip_sha: str) -> str:
    """Symlink ~/.hammerspoon/digivoice → checkout hammerspoon. Never copies."""
    if not (source / "init.lua").is_file():
        return f"adapter ...... missing source init.lua at {source}"
    target = user_adapter_dir(home)
    target.parent.mkdir(parents=True, exist_ok=True)
    resolved_source = source.resolve()
    if target.is_symlink():
        current = Path(os.path.realpath(target))
        if current == resolved_source:
            return f"adapter ...... symlink {target} -> {resolved_source}"
        target.unlink()
        target.symlink_to(resolved_source)
        return f"adapter ...... relinked symlink {target} -> {resolved_source}"
    if target.exists():
        guard_adapter_sync(dest=target, source_sha=tip_sha)
        return f"adapter ...... existing copy at {target} matches tip, left in place"
    target.symlink_to(resolved_source)
    return f"adapter ...... symlink {target} -> {resolved_source}"


def _maybe_fetch_model(
    models_dir: Path,
    runner: CommandRunner,
    fetch: bool,
) -> str:
    models_dir.mkdir(parents=True, exist_ok=True)
    dest = models_dir / DEFAULT_MODEL_FILE
    if dest.is_file():
        return f"models ....... {dest} (present)"
    if not fetch:
        return (
            f"models ....... dir {models_dir} (no {DEFAULT_MODEL_FILE}; "
            "pass --fetch-models or copy the weights in)"
        )
    dest.parent.mkdir(parents=True, exist_ok=True)
    result = runner(
        ["curl", "-fsSL", "--retry", "3", "-o", str(dest), DEFAULT_STT_MODEL_URL],
        timeout=180.0,
    )
    if result.code == 0 and dest.is_file():
        return f"models ....... fetched {dest}"
    dest.unlink(missing_ok=True)
    detail = (result.stderr or result.stdout or f"exit {result.code}").strip().splitlines()
    first = detail[0] if detail else "unknown"
    return f"models ....... fetch failed ({first}); place {DEFAULT_MODEL_FILE} in {models_dir}"


def _write_stamp(data_dir: Path, stamp: InstallStamp) -> None:
    data_dir.mkdir(parents=True, exist_ok=True)
    path = data_dir / INSTALL_STAMP
    temporary = path.with_name(f"{path.name}.tmp")
    temporary.write_text(stamp.model_dump_json(indent=2) + "\n", encoding="utf-8")
    os.replace(temporary, path)


def _reinstall_cli(runner: CommandRunner, package: Path) -> str:
    tool = runner(["uv", "tool", "install", "-e", str(package)], timeout=120.0)
    if tool.code == 0:
        return f"cli .......... uv tool install -e {package}"
    pip_uv = runner(["uv", "pip", "install", "-e", str(package)], timeout=120.0)
    if pip_uv.code == 0:
        return f"cli .......... uv pip install -e {package} (active venv)"
    pip = runner(["pip", "install", "-e", str(package)], timeout=120.0)
    if pip.code == 0:
        return f"cli .......... pip install -e {package}"
    return "cli .......... skipped (uv/pip install failed; CLI already running)"


def run_install(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    *,
    source_dir: Path | None = None,
    tip_sha: str | None = None,
    fetch_models: bool = False,
    reinstall_cli: bool = False,
    replace_app_support_adapter: bool = False,
    runner: CommandRunner | None = None,
    as_json: bool = False,
) -> CliResult:
    """Wire CLI + Hammerspoon symlink + models dir. Never hangs. No App Support rsync."""
    active = runner or run_command
    paths = resolve_paths(platform, home, env)
    source = _resolve_source(env, source_dir)
    checkout = repo_root() if source_dir is None else source.parent.parent.parent
    sha = _resolve_tip_sha(env, tip_sha, active, checkout)
    lines: list[str] = []
    payload: dict[str, object] = {"ok": True, "tip_sha": sha}
    code = 0

    Path(paths.models_dir).mkdir(parents=True, exist_ok=True)
    Path(paths.recordings_dir).mkdir(parents=True, exist_ok=True)

    app_support = app_support_hammerspoon(home)
    if app_support.exists() and not app_support.is_symlink():
        try:
            if replace_app_support_adapter:
                guard_adapter_sync(dest=app_support, source_sha=sha)
                lines.append(
                    f"app-support .. {app_support} matches tip {sha[:8]}, left in place (no rsync)"
                )
            else:
                dest_sha = read_tip_stamp(app_support) or "missing"
                lines.append(
                    f"app-support .. copy at {app_support} left alone "
                    f"(stamp={dest_sha}; no rsync). Live adapter is the ~/.hammerspoon symlink."
                )
        except AdapterGuardError as exc:
            lines.append(str(exc))
            payload["ok"] = False
            code = 1

    try:
        adapter_line = _link_user_adapter(home, source, sha)
        lines.append(adapter_line)
        payload["adapter"] = adapter_line
    except AdapterGuardError as exc:
        lines.append(str(exc))
        payload["ok"] = False
        code = 1

    config_line, _ = ensure_digivoice_require(home, paths)
    lines.append(config_line)

    if reinstall_cli:
        lines.append(_reinstall_cli(active, package_root()))
    else:
        cli = resolve_cli_path(env, home)
        lines.append(
            f"cli .......... {cli} (editable install; pass --reinstall-cli to refresh via uv tool)"
        )
        payload["cli"] = cli

    models_line = _maybe_fetch_model(Path(paths.models_dir), active, fetch_models)
    lines.append(models_line)
    payload["models"] = models_line

    stamp = InstallStamp(
        tip_sha=sha,
        adapter_source=str(source.resolve()) if source.exists() else str(source),
        adapter_target=str(user_adapter_dir(home)),
        cli=str(payload.get("cli", "digivoice")),
    )
    _write_stamp(Path(paths.data_dir), stamp)
    lines.append(f"stamp ........ {Path(paths.data_dir) / INSTALL_STAMP} tip {sha[:8]}")
    payload["stamp"] = stamp.model_dump()

    lines.append("next ......... digivoice doctor && digivoice reload && digivoice banner show")
    if as_json:
        payload["ok"] = code == 0
        return CliResult(code=code, stdout=json.dumps(payload, indent=2) + "\n", stderr="")
    return CliResult(code=code, stdout="\n".join(lines) + "\n", stderr="")


def _strip_require_line(home: Path) -> str:
    init = home / ".hammerspoon" / "init.lua"
    if not init.is_file():
        return "config ...... no init.lua"
    text = init.read_text(encoding="utf-8")
    kept = [
        line
        for line in text.splitlines(keepends=True)
        if line.strip() not in {'require("digivoice")', "require('digivoice')"}
    ]
    if len(kept) == len(text.splitlines(keepends=True)):
        return "config ...... require line not present"
    init.write_text("".join(kept), encoding="utf-8")
    return 'config ...... removed require("digivoice")'


def run_uninstall(
    platform: str,
    home: Path,
    env: Mapping[str, str],
    *,
    purge_data: bool = False,
    as_json: bool = False,
) -> CliResult:
    """Remove the user adapter symlink. Keep history/models unless --purge-data."""
    paths = resolve_paths(platform, home, env)
    lines: list[str] = []
    payload: dict[str, object] = {"ok": True}

    adapter = user_adapter_dir(home)
    if adapter.is_symlink() or adapter.exists():
        if adapter.is_symlink() or adapter.is_file():
            adapter.unlink()
            lines.append(f"adapter ...... removed {adapter}")
        else:
            lines.append(
                f"adapter ...... left {adapter} (real directory, not a symlink; "
                "delete it by hand if you installed a copy)"
            )
        payload["adapter_removed"] = True
    else:
        lines.append(f"adapter ...... already absent ({adapter})")
        payload["adapter_removed"] = False

    lines.append(_strip_require_line(home))

    stamp_path = Path(paths.data_dir) / INSTALL_STAMP
    if stamp_path.is_file():
        stamp_path.unlink()
        lines.append(f"stamp ........ removed {stamp_path}")

    if purge_data:
        data = Path(paths.data_dir)
        if data.exists():
            shutil.rmtree(data)
            lines.append(f"data ......... purged {data}")
            payload["data_purged"] = True
        else:
            lines.append(f"data ......... already absent ({data})")
            payload["data_purged"] = False
    else:
        lines.append(
            f"data ......... kept {paths.data_dir} (models, history). "
            "Pass --purge-data to delete it. Uninstall the CLI with: "
            "uv tool uninstall digivoice  (or uv pip / pip uninstall if installed in a venv)"
        )
        payload["data_purged"] = False

    lines.append("cli .......... not uninstalled automatically (uv/pip owns the console script)")
    if as_json:
        return CliResult(code=0, stdout=json.dumps(payload, indent=2) + "\n", stderr="")
    return CliResult(code=0, stdout="\n".join(lines) + "\n", stderr="")
