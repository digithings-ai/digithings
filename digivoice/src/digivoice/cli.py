"""digivoice command line. doctor, dict, speak, history, settings, cancel, and status are live."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from digivoice import history as history_log
from digivoice.capture import default_stop_file, discard_wav, record
from digivoice.doctor import doctor_checks, render_doctor
from digivoice.errors import CancelledError, EmptyTranscriptError, VoiceError
from digivoice.models import CliResult, PasteResult, VoicePaths
from digivoice.paste import copy_to_clipboard, paste
from digivoice.paths import DEFAULT_MODEL, resolve_paths
from digivoice.probe import CommandProbe, real_probe
from digivoice.rewrite import rewrite_transcript
from digivoice.runner import CommandRunner, cancellable_runner, run_command
from digivoice.settings import (
    VoiceSettings,
    format_settings_text,
    load_settings,
    set_setting,
    settings_path,
    settings_public_dict,
)
from digivoice.speak import read_clipboard, read_selection, speak
from digivoice.status import (
    CANCELLED_EXIT,
    CancelToken,
    StatusKind,
    StatusReporter,
    banner_flag_path,
    default_cancel_file,
    read_banner_flag,
    read_status,
    request_cancel,
    status_path,
    write_banner_flag,
)
from digivoice.transcribe import transcribe


class UsageError(Exception):
    def __init__(self, message: str) -> None:
        super().__init__(message)
        self.message = message


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        raise UsageError(message)


@dataclass(frozen=True)
class Runtime:
    platform: str
    home: Path
    env: Mapping[str, str]
    probe: CommandProbe
    # None means the real subprocess runner. Tests inject a fake instead.
    runner: CommandRunner | None = None
    # Optional rewrite backend injection for unit tests.
    rewrite_runner: object | None = None


def build_parser() -> _Parser:
    parser = _Parser(
        prog="digivoice",
        description=(
            "Local speech tools for macOS. whisper.cpp and Piper stay on this machine. "
            f"Default dictation model: {DEFAULT_MODEL}."
        ),
    )
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("doctor", help="Check whisper-cli, Piper, capture tools, and the model file")

    dictate = sub.add_parser("dict", help="Record the microphone, transcribe, and paste")
    mode = dictate.add_mutually_exclusive_group()
    mode.add_argument("--hold", action="store_true", help="Hold-to-talk length cap")
    mode.add_argument(
        "--toggle",
        action="store_true",
        help="Toggle recording: stop on SIGINT/SIGTERM or --stop-file (safety cap applies)",
    )
    dictate.add_argument(
        "--seconds",
        type=int,
        default=None,
        help="Override the recording cap in seconds",
    )
    dictate.add_argument(
        "--stop-file",
        default=None,
        help=(
            "Path touched to stop toggle recording early (default under the data dir when --toggle)"
        ),
    )
    dictate.add_argument(
        "--cancel-file",
        default=None,
        help=(
            "Path created to cancel the take: discard it, no paste, no history entry "
            "(default: dict.cancel under the data dir; `digivoice cancel` creates it)"
        ),
    )
    dictate.add_argument(
        "--no-paste",
        action="store_true",
        help="Skip pasting into the focused app",
    )
    dictate.add_argument(
        "--no-rewrite",
        action="store_true",
        help="Skip post-STT local rewrite even when enabled in settings",
    )

    speak_cmd = sub.add_parser("speak", help="Speak text with Piper")
    source = speak_cmd.add_mutually_exclusive_group()
    source.add_argument("--clipboard", action="store_true", help="Read the clipboard")
    source.add_argument("--selection", action="store_true", help="Read the selection")
    source.add_argument(
        "--clipboard-or-history",
        action="store_true",
        help=(
            "Read the clipboard only (no history fallback). "
            "Hammerspoon speak hotkey uses --selection instead."
        ),
    )
    speak_cmd.add_argument("text", nargs="*", help="Text to speak")

    history = sub.add_parser("history", help="List dictation history entries")
    history.add_argument("--last", type=int, default=None, help="Limit to the last N entries")
    history.add_argument("--grep", default=None, help="Filter entries by pattern")
    history.add_argument(
        "--copy-last",
        action="store_true",
        help="Copy the most recent non-empty dict transcript to the clipboard",
    )
    history.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print matching entries as JSON (agent-readable)",
    )

    cancel_cmd = sub.add_parser(
        "cancel", help="Cancel the running dict take: discard it, no paste, no history entry"
    )
    cancel_cmd.add_argument(
        "--cancel-file", default=None, help="Cancel-file path (default under the data dir)"
    )
    sub.add_parser("status", help="Print the live status.json the banner reads")

    banner_cmd = sub.add_parser(
        "banner",
        help="Show or hide the Hammerspoon banner preview (no dictation needed)",
    )
    banner_cmd.add_argument(
        "action",
        nargs="?",
        default="show",
        choices=["show", "hide", "toggle"],
        help="show (default), hide, or toggle the preview banner",
    )
    banner_cmd.add_argument(
        "--text",
        default="",
        help="Preview text to typeset (show only)",
    )

    settings_cmd = sub.add_parser(
        "settings",
        help="Show or change digivoice settings (models, rewrite, features)",
    )
    settings_sub = settings_cmd.add_subparsers(dest="settings_command")
    settings_cmd.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print settings as JSON (includes paths and hotkey docs)",
    )
    get_cmd = settings_sub.add_parser("get", help="Print one setting value")
    get_cmd.add_argument("key", help="Setting key (e.g. rewrite_enabled)")
    set_cmd = settings_sub.add_parser("set", help="Set one setting value and persist")
    set_cmd.add_argument("key", help="Setting key")
    set_cmd.add_argument("value", help="New value (true/false, preset name, path, …)")
    settings_sub.add_parser("path", help="Print the settings.json path")
    setup = sub.add_parser(
        "setup",
        help="Interactive setup wizard (models, features, hotkeys, hardware stub, doctor)",
    )
    setup.add_argument(
        "--json",
        action="store_true",
        dest="as_json",
        help="Print settings + menu tree as JSON (no prompts)",
    )
    setup.add_argument(
        "--print",
        action="store_true",
        dest="print_only",
        help="Print current settings + menu tree (no prompts; same as env noninteractive)",
    )
    sub.add_parser("update", help="Reinstall hint (not wired yet)")
    sub.add_parser("uninstall", help="Removal hint (not wired yet)")
    return parser


def _usage(message: str) -> CliResult:
    return CliResult(code=2, stdout="", stderr=f"{message}\n")


def _doctor(runtime: Runtime) -> CliResult:
    report = render_doctor(
        doctor_checks(runtime.platform, runtime.home, dict(runtime.env), runtime.probe)
    )
    return CliResult(code=0 if report.ok else 1, stdout=report.text, stderr="")


def _notes(lines: list[str]) -> str:
    return "".join(f"digivoice: {line}\n" for line in lines)


def _setup(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    """Real setup entry: interactive wizard, or print/json for agents."""
    import json as _json

    from digivoice.setup import (
        render_setup_overview,
        run_interactive_setup,
        setup_public_dict,
    )

    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    settings = load_settings(paths)
    noninteractive = bool(getattr(args, "print_only", False)) or bool(
        runtime.env.get("DIGIVOICE_SETUP_NONINTERACTIVE", "")
    )
    if bool(getattr(args, "as_json", False)):
        payload = setup_public_dict(settings, paths)
        return CliResult(code=0, stdout=_json.dumps(payload, indent=2) + "\n", stderr="")
    if noninteractive:
        return CliResult(code=0, stdout=render_setup_overview(settings, paths) + "\n", stderr="")
    if not sys.stdin.isatty():
        # Never hang an agent/pipe waiting for arrow keys: print instead.
        return CliResult(
            code=0,
            stdout=render_setup_overview(settings, paths) + "\n",
            stderr="digivoice: stdin is not a TTY; printed setup instead of the wizard\n",
        )
    report = render_doctor(
        doctor_checks(runtime.platform, runtime.home, dict(runtime.env), runtime.probe)
    )
    code = run_interactive_setup(paths, run_doctor=lambda: report.text)
    return CliResult(code=code, stdout="", stderr="")


def _update() -> CliResult:
    return CliResult(
        code=0,
        stdout="digivoice update: not wired yet — reinstall via uv / brew when available\n",
        stderr="",
    )


def _uninstall() -> CliResult:
    return CliResult(
        code=0,
        stdout=(
            "digivoice uninstall: not wired yet — "
            "remove the uv tool install and the data dir manually\n"
        ),
        stderr="",
    )


def _runner(runtime: Runtime) -> CommandRunner:
    return runtime.runner or run_command


def _banner_reporter(
    paths: VoicePaths, settings: VoiceSettings, kind: StatusKind
) -> StatusReporter:
    """Status feed for the banner. Off (a no-op reporter) when live_banner is false."""
    return StatusReporter(status_path(paths) if settings.live_banner else None, kind)


def _cancelled(reporter: StatusReporter, wav_path: str | None = None) -> CliResult:
    """A cancelled take leaves nothing behind: no wav, no history line, no paste."""
    discard_wav(wav_path)
    reporter.update("cancelled", detail="take discarded")
    return CliResult(
        code=CANCELLED_EXIT,
        stdout="",
        stderr="digivoice dict: cancelled; nothing saved, pasted, or added to history\n",
    )


def _dict(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    if args.hold:
        mode = "hold"
    elif args.toggle:
        mode = "toggle"
    else:
        mode = "default"
    if args.seconds is not None and args.seconds < 1:
        return _usage("--seconds expects a positive integer")
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    settings = load_settings(paths)
    reporter = _banner_reporter(paths, settings, "dict")
    cancel = CancelToken(args.cancel_file or default_cancel_file(paths))
    # A cancel left over from an earlier take must not kill this one.
    cancel.clear()
    try:
        return _dict_take(args, runtime, mode, paths, settings, reporter, cancel)
    finally:
        cancel.clear()


def _dict_take(
    args: argparse.Namespace,
    runtime: Runtime,
    mode: str,
    paths: VoicePaths,
    settings: VoiceSettings,
    reporter: StatusReporter,
    cancel: CancelToken,
) -> CliResult:
    runner = _runner(runtime)
    stage_runner = cancellable_runner(runner, cancel.requested)
    notes: list[str] = []
    stop_file = args.stop_file
    if mode == "toggle" and not stop_file:
        stop_file = str(default_stop_file(paths))
    early_stop = mode == "toggle"
    reporter.update("recording")
    try:
        recording = record(
            paths,
            runtime.probe,
            runner,
            mode=mode,
            seconds=args.seconds,
            platform=runtime.platform,
            stop_file=stop_file,
            early_stop=early_stop,
            cancel=cancel,
        )
    except CancelledError:
        return _cancelled(reporter)
    except VoiceError as exc:
        reporter.update("error", detail=str(exc))
        return CliResult(code=1, stdout="", stderr=f"digivoice dict: {exc}\n")
    if cancel.requested():
        return _cancelled(reporter, recording.wav_path)
    note = f"recorded {recording.seconds}s with {recording.tool}"
    if recording.stopped_early:
        note += " (stopped early — wav kept; pasting what was captured)"
    notes.append(note)
    reporter.update("transcribing")
    try:
        transcript = transcribe(paths, runtime.probe, stage_runner, recording.wav_path)
    except VoiceError as exc:
        if cancel.requested():
            return _cancelled(reporter, recording.wav_path)
        if isinstance(exc, EmptyTranscriptError):
            # Silence is not a take: drop the wav, never paste or log a blank.
            discard_wav(recording.wav_path)
            reporter.update("empty", detail="nothing recognized")
            return CliResult(
                code=1,
                stdout="",
                stderr=_notes(notes)
                + f"digivoice dict: {exc}; take discarded (no paste, no history entry)\n",
            )
        notes.append(f"audio kept at {recording.wav_path}")
        reporter.update("error", detail=str(exc))
        return CliResult(code=1, stdout="", stderr=_notes(notes) + f"digivoice dict: {exc}\n")
    if cancel.requested():
        return _cancelled(reporter, recording.wav_path)
    notes.append(f"transcribed with {transcript.model}")
    text_out = transcript.text
    will_paste = not args.no_paste and settings.paste_on_stop
    if args.no_rewrite:
        notes.append("rewrite skipped (--no-rewrite)")
    else:
        if settings.rewrite_enabled:
            reporter.update(
                "rewriting",
                text=transcript.text,
                detail=f"preset {settings.rewrite_preset}",
            )
        rewritten = rewrite_transcript(
            transcript.text,
            paths=paths,
            settings=settings,
            probe=runtime.probe,
            runner=stage_runner,
            platform=runtime.platform,
            rewrite_runner=runtime.rewrite_runner,  # type: ignore[arg-type]
        )
        text_out = rewritten.text
        notes.append(rewritten.detail)
    if not text_out.strip():
        discard_wav(recording.wav_path)
        reporter.update("empty", detail="nothing recognized")
        return CliResult(
            code=1,
            stdout="",
            stderr=_notes(notes) + "digivoice dict: empty text; take discarded "
            "(no paste, no history entry)\n",
        )
    reporter.update(
        "pasting" if will_paste else "transcribing",
        text=text_out,
        detail="rewritten" if text_out != transcript.text else "",
    )
    # Last chance to cancel: once the history line is written the take is committed.
    if cancel.requested():
        return _cancelled(reporter, recording.wav_path)
    history_file = paths.history_file
    try:
        history_log.append_entry(history_file, history_log.dict_entry(text_out, recording.wav_path))
    except OSError as exc:
        # A transcript the user can see beats failing the whole dictation.
        notes.append(f"history append failed ({exc})")
    else:
        notes.append(f"history {history_file}")
    if args.no_paste:
        pasted = PasteResult(attempted=False, pasted=False, detail="skipped (--no-paste)")
    elif not settings.paste_on_stop:
        pasted = PasteResult(
            attempted=False,
            pasted=False,
            detail="skipped (paste_on_stop=false in settings)",
        )
    else:
        pasted = paste(runtime.platform, runtime.probe, runner, text_out)
    notes.append(f"paste {pasted.detail}")
    reporter.update("done", text=text_out, detail=pasted.detail)
    return CliResult(code=0, stdout=f"{text_out}\n", stderr=_notes(notes))


def _resolve_speak_text(args: argparse.Namespace, runtime: Runtime) -> str:
    text = " ".join(args.text).strip()
    source_flags = sum(
        1 for flag in (args.clipboard, args.selection, args.clipboard_or_history) if flag
    )
    if source_flags and text:
        raise UsageError("pass text or one of --clipboard, --selection, --clipboard-or-history")
    if source_flags > 1:
        raise UsageError("pass only one of --clipboard, --selection, --clipboard-or-history")
    runner = _runner(runtime)
    if args.clipboard:
        return read_clipboard(runtime.platform, runtime.probe, runner)
    if args.selection:
        return read_selection(runtime.platform, runtime.probe, runner)
    if args.clipboard_or_history:
        # Kept for CLI callers; does NOT fall back to history (esp. not kind:dict).
        return read_clipboard(runtime.platform, runtime.probe, runner)
    if text:
        return text
    raise UsageError("speak needs text, --clipboard, --selection, or --clipboard-or-history")


def _speak(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    reporter = _banner_reporter(paths, load_settings(paths), "speak")
    reporter.update("loading")
    try:
        text = _resolve_speak_text(args, runtime)
    except UsageError as exc:
        return _usage(exc.message)
    except VoiceError as exc:
        reporter.update("error", detail=str(exc))
        return CliResult(code=1, stdout="", stderr=f"digivoice speak: {exc}\n")
    reporter.update("speaking", text=text)
    runner = _runner(runtime)
    notes: list[str] = []
    try:
        spoken = speak(
            paths,
            runtime.probe,
            runner,
            text,
            platform=runtime.platform,
            home=runtime.home,
            env=runtime.env,
        )
    except VoiceError as exc:
        reporter.update("error", detail=str(exc))
        return CliResult(code=1, stdout="", stderr=f"digivoice speak: {exc}\n")
    notes.append(f"voice {spoken.voice_path}")
    notes.append(f"played with {spoken.player}")
    history_file = paths.history_file
    try:
        history_log.append_entry(history_file, history_log.speak_entry(spoken.text))
    except OSError as exc:
        notes.append(f"history append failed ({exc})")
    else:
        notes.append(f"history {history_file}")
    reporter.update("done", text=spoken.text)
    return CliResult(code=0, stdout=f"{spoken.text}\n", stderr=_notes(notes))


def _cancel(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    target = args.cancel_file or default_cancel_file(paths)
    try:
        request_cancel(target)
    except OSError as exc:
        return CliResult(code=1, stdout="", stderr=f"digivoice cancel: {exc}\n")
    return CliResult(
        code=0,
        stdout=f"{target}\n",
        stderr="digivoice: cancel requested; a running dict take discards itself\n",
    )


def _status(runtime: Runtime) -> CliResult:
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    snapshot = read_status(status_path(paths))
    if snapshot is None:
        return CliResult(
            code=1,
            stdout="",
            stderr=f"digivoice status: no status yet ({status_path(paths)})\n",
        )
    return CliResult(code=0, stdout=snapshot.model_dump_json(indent=2) + "\n", stderr="")


def _banner(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    """Spawn-flag for the banner preview. The adapter polls it; no dictation."""
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    flag = banner_flag_path(paths)
    action = args.action
    if action == "toggle":
        current = read_banner_flag(flag)
        action = "hide" if current and current.get("visible") else "show"
    try:
        if action == "hide":
            write_banner_flag(flag, visible=False)
            return CliResult(code=0, stdout=f"{flag}\n", stderr="digivoice: banner hidden\n")
        write_banner_flag(flag, visible=True, text=args.text or "")
    except OSError as exc:
        return CliResult(code=1, stdout="", stderr=f"digivoice banner: {exc}\n")
    return CliResult(code=0, stdout=f"{flag}\n", stderr="digivoice: banner shown\n")


def _history(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    if args.last is not None and args.last < 1:
        return _usage("--last expects a positive integer")
    if args.grep is not None and not args.grep:
        return _usage("--grep expects a pattern")
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    reading = history_log.read_history(paths.history_file)
    if args.copy_last:
        text = history_log.last_dict_text(paths.history_file)
        if text is None:
            return CliResult(
                code=1,
                stdout="",
                stderr="digivoice history: no dict entry to copy\n",
            )
        copied = copy_to_clipboard(runtime.platform, runtime.probe, _runner(runtime), text)
        if not copied.pasted:
            return CliResult(
                code=1,
                stdout="",
                stderr=f"digivoice history: {copied.detail}\n",
            )
        return CliResult(
            code=0,
            stdout=f"{text}\n",
            stderr=f"digivoice: {copied.detail}\n",
        )
    filters: list[str] = []
    if args.last is not None:
        filters.append(f"--last {args.last}")
    if args.grep is not None:
        filters.append(f"--grep {args.grep}")
    if getattr(args, "as_json", False):
        picked = history_log.select(reading.entries, last=args.last, grep=args.grep)
        payload = {
            "file": paths.history_file,
            "present": reading.present,
            "skipped": reading.skipped,
            "count": len(picked),
            "total": len(reading.entries),
            "entries": [entry.model_dump(mode="json") for entry in picked],
        }
        return CliResult(code=0, stdout=json.dumps(payload, indent=2) + "\n", stderr="")
    lines = [f"file: {paths.history_file}"]
    if filters:
        lines.append(f"filters: {', '.join(filters)}")
    if not reading.present:
        lines.append(f"no history file yet: {paths.history_file}")
    else:
        picked = history_log.select(reading.entries, last=args.last, grep=args.grep)
        if reading.skipped:
            lines.append(f"skipped {reading.skipped} unreadable line(s)")
        lines.append(
            f"{len(picked)} of {len(reading.entries)} "
            f"{'entry' if len(reading.entries) == 1 else 'entries'}"
        )
        lines.append("")
        lines.extend(history_log.format_entry(entry) for entry in picked)
        if not picked:
            lines.append("no matching entries")
    return CliResult(code=0, stdout="\n".join(lines) + "\n", stderr="")


def _settings(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    sub = getattr(args, "settings_command", None)
    as_json = bool(getattr(args, "as_json", False))
    if sub == "path":
        return CliResult(code=0, stdout=f"{settings_path(paths)}\n", stderr="")
    if sub == "get":
        settings = load_settings(paths)
        if args.key not in VoiceSettings.model_fields:
            known = ", ".join(sorted(VoiceSettings.model_fields))
            return _usage(f"unknown setting {args.key!r}; known: {known}")
        value = getattr(settings, args.key)
        if as_json:
            return CliResult(
                code=0,
                stdout=json.dumps({args.key: value}) + "\n",
                stderr="",
            )
        if value is None:
            return CliResult(code=0, stdout="null\n", stderr="")
        if isinstance(value, bool):
            return CliResult(code=0, stdout=("true" if value else "false") + "\n", stderr="")
        return CliResult(code=0, stdout=f"{value}\n", stderr="")
    if sub == "set":
        try:
            settings = set_setting(paths, args.key, args.value)
        except KeyError:
            known = ", ".join(sorted(VoiceSettings.model_fields))
            return _usage(f"unknown setting {args.key!r}; known: {known}")
        except (ValueError, Exception) as exc:
            return CliResult(code=2, stdout="", stderr=f"digivoice settings: {exc}\n")
        if as_json:
            return CliResult(
                code=0,
                stdout=json.dumps(settings_public_dict(settings, paths), indent=2) + "\n",
                stderr=f"digivoice: saved {settings_path(paths)}\n",
            )
        return CliResult(
            code=0,
            stdout=format_settings_text(settings, paths),
            stderr=f"digivoice: saved {settings_path(paths)}\n",
        )
    # show
    settings = load_settings(paths)
    if as_json:
        return CliResult(
            code=0,
            stdout=json.dumps(settings_public_dict(settings, paths), indent=2) + "\n",
            stderr="",
        )
    return CliResult(code=0, stdout=format_settings_text(settings, paths), stderr="")


def run(argv: Sequence[str], runtime: Runtime) -> CliResult:
    parser = build_parser()
    if not argv or argv[0] in {"help", "-h", "--help"}:
        return CliResult(code=0, stdout=parser.format_help(), stderr="")
    try:
        args = parser.parse_args(list(argv))
    except UsageError as exc:
        return CliResult(code=2, stdout="", stderr=f"{exc.message}\n\n{parser.format_help()}")
    command = args.command
    if command == "doctor":
        return _doctor(runtime)
    if command == "dict":
        return _dict(args, runtime)
    if command == "speak":
        return _speak(args, runtime)
    if command == "cancel":
        return _cancel(args, runtime)
    if command == "status":
        return _status(runtime)
    if command == "banner":
        return _banner(args, runtime)
    if command == "history":
        return _history(args, runtime)
    if command in {"settings", "setup"}:
        if command == "setup":
            if not hasattr(args, "as_json"):
                args.as_json = False
            if not hasattr(args, "print_only"):
                args.print_only = False
            return _setup(args, runtime)
        if not hasattr(args, "settings_command"):
            args.settings_command = None
        if not hasattr(args, "as_json"):
            args.as_json = False
        return _settings(args, runtime)
    if command == "update":
        return _update()
    if command == "uninstall":
        return _uninstall()
    return _usage(f"unknown command: {command}")


def main(argv: Sequence[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv[1:]
    runtime = Runtime(
        platform=sys.platform,
        home=Path.home(),
        env=os.environ,
        probe=real_probe(os.environ.get("PATH")),
        runner=run_command,
    )
    result = run(argv, runtime)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.code
