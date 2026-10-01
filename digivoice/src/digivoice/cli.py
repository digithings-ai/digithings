"""digivoice command line. doctor, dict, speak, and history are live."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from digivoice import history as history_log
from digivoice.capture import default_stop_file, record
from digivoice.doctor import doctor_checks, render_doctor
from digivoice.errors import VoiceError
from digivoice.models import CliResult, PasteResult
from digivoice.paste import paste
from digivoice.paths import DEFAULT_MODEL, resolve_paths
from digivoice.probe import CommandProbe, real_probe
from digivoice.runner import CommandRunner, run_command
from digivoice.speak import read_clipboard, read_selection, speak
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
        "--no-paste",
        action="store_true",
        help="Skip pasting into the focused app",
    )

    speak_cmd = sub.add_parser("speak", help="Speak text with Piper")
    source = speak_cmd.add_mutually_exclusive_group()
    source.add_argument("--clipboard", action="store_true", help="Read the clipboard")
    source.add_argument("--selection", action="store_true", help="Read the selection")
    source.add_argument(
        "--clipboard-or-history",
        action="store_true",
        help="Prefer clipboard text; else the last digivoice history entry",
    )
    speak_cmd.add_argument("text", nargs="*", help="Text to speak")

    history = sub.add_parser("history", help="List dictation history entries")
    history.add_argument("--last", type=int, default=None, help="Limit to the last N entries")
    history.add_argument("--grep", default=None, help="Filter entries by pattern")
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


def _runner(runtime: Runtime) -> CommandRunner:
    return runtime.runner or run_command


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
    runner = _runner(runtime)
    notes: list[str] = []
    stop_file = args.stop_file
    if mode == "toggle" and not stop_file:
        stop_file = str(default_stop_file(paths))
    early_stop = mode == "toggle"
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
        )
    except VoiceError as exc:
        return CliResult(code=1, stdout="", stderr=f"digivoice dict: {exc}\n")
    note = f"recorded {recording.seconds}s with {recording.tool}"
    if recording.stopped_early:
        note += " (stopped early)"
    notes.append(note)
    try:
        transcript = transcribe(paths, runtime.probe, runner, recording.wav_path)
    except VoiceError as exc:
        notes.append(f"audio kept at {recording.wav_path}")
        return CliResult(code=1, stdout="", stderr=_notes(notes) + f"digivoice dict: {exc}\n")
    notes.append(f"transcribed with {transcript.model}")
    history_file = paths.history_file
    try:
        history_log.append_entry(
            history_file, history_log.dict_entry(transcript.text, recording.wav_path)
        )
    except OSError as exc:
        # A transcript the user can see beats failing the whole dictation.
        notes.append(f"history append failed ({exc})")
    else:
        notes.append(f"history {history_file}")
    if args.no_paste:
        pasted = PasteResult(attempted=False, pasted=False, detail="skipped (--no-paste)")
    else:
        pasted = paste(runtime.platform, runtime.probe, runner, transcript.text)
    notes.append(f"paste {pasted.detail}")
    return CliResult(code=0, stdout=f"{transcript.text}\n", stderr=_notes(notes))


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
        try:
            return read_clipboard(runtime.platform, runtime.probe, runner)
        except VoiceError:
            paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
            last = history_log.last_speakable_text(paths.history_file)
            if last:
                return last
            raise VoiceError("clipboard is empty and history has nothing to speak") from None
    if text:
        return text
    raise UsageError("speak needs text, --clipboard, --selection, or --clipboard-or-history")


def _speak(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    try:
        text = _resolve_speak_text(args, runtime)
    except UsageError as exc:
        return _usage(exc.message)
    except VoiceError as exc:
        return CliResult(code=1, stdout="", stderr=f"digivoice speak: {exc}\n")
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
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
    return CliResult(code=0, stdout=f"{spoken.text}\n", stderr=_notes(notes))


def _history(args: argparse.Namespace, runtime: Runtime) -> CliResult:
    if args.last is not None and args.last < 1:
        return _usage("--last expects a positive integer")
    if args.grep is not None and not args.grep:
        return _usage("--grep expects a pattern")
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    reading = history_log.read_history(paths.history_file)
    filters: list[str] = []
    if args.last is not None:
        filters.append(f"--last {args.last}")
    if args.grep is not None:
        filters.append(f"--grep {args.grep}")
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
    if command == "history":
        return _history(args, runtime)
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
