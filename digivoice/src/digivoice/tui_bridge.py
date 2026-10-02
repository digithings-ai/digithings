"""JSON screen model for the OpenTUI process. Local stdin/stdout only."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from typing import Any

from digivoice.catalog import install_catalog_model
from digivoice.doctor import doctor_checks
from digivoice.history import delete_entry, read_history
from digivoice.home import HOME_BLOCKS, build_context_lines
from digivoice.installed_models import discover_installed_models
from digivoice.menu_tree import TreeRow, _changed, _missing_catalog, rows_at
from digivoice.models import HistoryEntry
from digivoice.nav import norm_path
from digivoice.opentui import NAV_FOOTER
from digivoice.panels import _UPDATE, SYSTEM_BLOCKS
from digivoice.paste import copy_to_clipboard
from digivoice.paths import resolve_paths
from digivoice.probe import real_probe
from digivoice.reload import run_reload, stop_home_control
from digivoice.runner import run_command
from digivoice.settings import default_settings, load_settings, save_settings
from digivoice.status import read_system_log, system_log_path

_PAGE = 8


def _row(row: TreeRow, path: str) -> dict[str, str]:
    block = row.as_block(path)
    return {
        "action": block.action,
        "path": block.path,
        "meta": block.meta or "",
        "kind": row.kind,
        "name": row.name,
        "choice": row.choice,
    }


def _settings_rows(paths: Any, path: str) -> list[dict[str, str]]:
    settings = load_settings(paths)
    installed = discover_installed_models(Path.home(), dict(os_environ()))
    rows = rows_at(settings, path, Path(paths.models_dir), installed)
    return [_row(row, path) for row in rows]


def os_environ() -> dict[str, str]:
    return dict(os.environ)


def _history_page(paths: Any, page: int) -> dict[str, Any]:
    ordered = list(reversed(read_history(paths.history_file).entries))
    if not ordered:
        return {
            "title": "History",
            "path": "/history",
            "page": 1,
            "pages": 1,
            "paging": False,
            "rows": [{"action": "No takes yet", "path": "/history", "meta": "", "kind": "note"}],
        }
    pages = max(1, (len(ordered) + _PAGE - 1) // _PAGE)
    page = min(max(0, page), pages - 1)
    visible = ordered[page * _PAGE : (page + 1) * _PAGE]
    rows = [
        {
            "action": entry.text,
            "path": "/history",
            "meta": entry.ts,
            "kind": "take",
            "index": index,
        }
        for index, entry in enumerate(visible)
    ]
    label = f"/history  {page + 1}/{pages}" if pages > 1 else "/history"
    return {
        "title": "History",
        "path": label,
        "page": page + 1,
        "pages": pages,
        "paging": pages > 1,
        "rows": rows,
    }


def _take(paths: Any, page: int, index: int) -> HistoryEntry | None:
    ordered = list(reversed(read_history(paths.history_file).entries))
    start = max(0, page) * _PAGE
    visible = ordered[start : start + _PAGE]
    if not 0 <= index < len(visible):
        return None
    return visible[index]


def dispatch(
    req: dict[str, Any], *, platform: str, home: Path, env: dict[str, str]
) -> dict[str, Any]:
    """One screen request. Missing apps and unknown ops return data, not a traceback."""
    paths = resolve_paths(platform, home, env)
    op = str(req.get("op") or "boot")
    footer = NAV_FOOTER
    if op == "boot":
        start = norm_path(str(req.get("start") or env.get("DIGIVOICE_TUI_START") or "/"))
        context = build_context_lines(platform, home, env, probe=real_probe(env.get("PATH", "")))
        return {
            "footer": footer,
            "context": context,
            "start": start,
            "home": [_row_block(block) for block in HOME_BLOCKS],
            "screen": _open_path(paths, platform, home, env, start),
        }
    if op == "rows":
        path = norm_path(str(req.get("path") or "/settings"))
        return {"footer": footer, "path": path, "rows": _settings_rows(paths, path)}
    if op == "apply":
        return _apply(paths, req)
    if op == "history":
        page = int(req.get("page") or 1) - 1
        payload = _history_page(paths, page)
        payload["footer"] = footer
        return payload
    if op == "history-copy":
        entry = _take(paths, int(req.get("page") or 1) - 1, int(req.get("index") or 0))
        if entry is None:
            return {"footer": footer, "note": "no takes yet"}
        copied = copy_to_clipboard(
            platform, real_probe(env.get("PATH", "")), run_command, entry.text
        )
        return {"footer": footer, "note": copied.detail}
    if op == "history-delete":
        entry = _take(paths, int(req.get("page") or 1) - 1, int(req.get("index") or 0))
        if entry is None:
            return {"footer": footer, "note": "no takes yet"}
        delete_entry(paths.history_file, entry)
        return {
            "footer": footer,
            "note": "deleted",
            **_history_page(paths, int(req.get("page") or 1) - 1),
        }
    if op == "system":
        return {
            "footer": footer,
            "title": "System",
            "path": "/system",
            "rows": [_row_block(block) for block in SYSTEM_BLOCKS],
        }
    if op == "doctor":
        checks = doctor_checks(platform, home, env, real_probe(env.get("PATH", "")))
        rows = [
            {"action": check.detail, "path": "/doctor", "meta": check.status, "kind": "note"}
            for check in checks
        ]
        required = {"whisper-cli", "piper", "capture", "models"}
        ok = all(check.status != "missing" for check in checks if check.id in required)
        return {"footer": footer, "title": "Doctor", "path": "/doctor", "rows": rows, "ok": ok}
    if op == "logs":
        text = read_system_log(system_log_path(paths)).strip()
        lines = [line for line in text.splitlines() if line.strip()] or ["No log yet"]
        return {
            "footer": footer,
            "title": "Logs",
            "path": "/system/logs",
            "rows": [
                {"action": line, "path": "/system/logs", "meta": "", "kind": "note"}
                for line in lines
            ],
        }
    if op == "reload":
        result = run_reload(platform, home, env, runner=run_command)
        note = result.stdout.strip() or result.stderr.strip() or "reload finished"
        return {"footer": footer, "note": note}
    if op == "reset":
        save_settings(paths, default_settings())
        return {"footer": footer, "note": "settings reset"}
    if op == "restart":
        return {"footer": footer, "restart": True}
    if op == "update":
        return {"footer": footer, "note": _UPDATE}
    if op == "quit":
        report = stop_home_control(platform, home, env, runner=run_command)
        return {"footer": footer, "exit": 0, "stopped": True, "note": report.summary}
    if op == "close":
        return {"footer": footer, "exit": 0, "stopped": False}
    return {"footer": footer, "error": f"unknown op {op}"}


def _row_block(block: Any) -> dict[str, str]:
    return {
        "action": block.action,
        "path": block.path,
        "meta": "",
        "kind": "dir",
        "name": block.action,
        "choice": "",
    }


def _open_path(
    paths: Any,
    platform: str,
    home: Path,
    env: dict[str, str],
    start: str,
) -> dict[str, Any]:
    if start in {"", "/"}:
        return {
            "title": "Actions",
            "path": "/",
            "rows": [_row_block(block) for block in HOME_BLOCKS],
            "paging": False,
        }
    if start.startswith("/settings"):
        return {
            "title": start.rsplit("/", 1)[-1],
            "path": start,
            "rows": _settings_rows(paths, start),
            "paging": False,
        }
    if start.startswith("/history"):
        return _history_page(paths, 0)
    if start == "/system/logs":
        return dispatch({"op": "logs"}, platform=platform, home=home, env=env)
    if start == "/doctor":
        return dispatch({"op": "doctor"}, platform=platform, home=home, env=env)
    if start.startswith("/system"):
        return dispatch({"op": "system"}, platform=platform, home=home, env=env)
    return {
        "title": "Actions",
        "path": "/",
        "rows": [_row_block(block) for block in HOME_BLOCKS],
        "paging": False,
    }


def _apply(paths: Any, req: dict[str, Any]) -> dict[str, Any]:
    path = norm_path(str(req.get("path") or "/settings"))
    settings = load_settings(paths)
    installed = discover_installed_models(Path.home(), dict(os_environ()))
    rows = rows_at(settings, path, Path(paths.models_dir), installed)
    index = int(req.get("index") or 0)
    if not rows or not 0 <= index < len(rows):
        return {"error": "no row"}
    row = rows[index]
    if row.kind in {"dir", "pick"}:
        child = f"{path}/{row.name}"
        return {
            "open": child,
            "rows": _settings_rows(paths, child),
            "title": row.name,
            "path": child,
        }
    if row.kind == "capture":
        text = req.get("text")
        if not isinstance(text, str) or not text.strip():
            return {"capture": True, "name": row.name}
        nxt = _changed(settings, row, text.strip())
        if nxt is None:
            return {"note": "binding unchanged"}
        save_settings(paths, nxt)
        return {"saved": True, "rows": _settings_rows(paths, path)}
    if row.kind != "choice":
        return {"note": row.explain}
    missing = _missing_catalog(paths, row)
    if missing is not None and not req.get("confirm"):
        return {
            "confirm": True,
            "title": missing.title,
            "rows": [
                {
                    "action": f"Download ({missing.size_hint})",
                    "path": path,
                    "meta": "",
                    "kind": "confirm",
                },
                {"action": "Back", "path": path, "meta": "", "kind": "back"},
            ],
        }
    if missing is not None and req.get("confirm"):
        try:
            install_catalog_model(paths, missing)
        except (OSError, ValueError) as exc:
            return {"error": f"could not install {missing.filename}: {exc}"}
    nxt = _changed(settings, row, None)
    if nxt is None:
        return {"note": "unchanged"}
    save_settings(paths, nxt)
    parent = path.rsplit("/", 1)[0] or "/settings"
    return {
        "saved": True,
        "path": parent,
        "rows": _settings_rows(paths, parent),
        "title": parent.rsplit("/", 1)[-1],
    }


def main(argv: list[str] | None = None) -> int:
    _ = argv
    raw = sys.stdin.read()
    try:
        req = json.loads(raw) if raw.strip() else {}
    except json.JSONDecodeError:
        sys.stdout.write(json.dumps({"error": "invalid json"}))
        return 0
    if not isinstance(req, dict):
        sys.stdout.write(json.dumps({"error": "invalid json"}))
        return 0
    env = dict(os.environ)
    result = dispatch(req, platform=sys.platform, home=Path.home(), env=env)
    sys.stdout.write(json.dumps(result))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
