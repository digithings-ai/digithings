"""digivoice command line. doctor, dict, and history are live; speak is a stub."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from digivoice import history as history_log
from digivoice.capture import record
from digivoice.doctor import doctor_checks, render_doctor
from digivoice.errors import VoiceError
from digivoice.models import CliResult, PasteResult
from digivoice.paste import paste
from digivoice.paths import DEFAULT_MODEL, resolve_paths
from digivoice.probe import CommandProbe, real_probe
from digivoice.runner import CommandRunner, run_command
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
    mode.add_argument("--toggle", action="store_true", help="Toggle-recording length cap")
    dictate.add_argument(
        "--seconds",
        type=int,
        default=None,
        help="Override the recording cap in seconds",
    )
    dictate.add_argument(
        "--no-paste",
        action="store_true",
        help="Skip pasting into the focused app",
    )

    speak = sub.add_parser("speak", help="Speak text with Piper (stub until PR2)")
    source = speak.add_mutually_exclusive_group()
    source.add_argument("--clipboard", action="store_true", help="Read the clipboard")
    source.add_argument("--selection", action="store_true", help="Read the selection")
    speak.add_argument("text", nargs="*", help="Text to speak")

    history = sub.add_parser("history", help="List dictation history entries")
    history.add_argument("--last", type=int, default=None, help="Limit to the last N entries")
    history.add_argument("--grep", default=None, help="Filter entries by pattern")
    return parser


def _usage(message: str) -> CliResult:
    return CliResult(code=2, stdout="", stderr=f"{message}\n")


def _stub(stderr: str) -> CliResult:
    return CliResult(code=2, stdout="", stderr=stderr)


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
    try:
        recording = record(
            paths,
            runtime.probe,
            runner,
            mode=mode,
            seconds=args.seconds,
            platform=runtime.platform,
        )
    except VoiceError as exc:
        return CliResult(code=1, stdout="", stderr=f"digivoice dict: {exc}\n")
    notes.append(f"recorded {recording.seconds}s with {recording.tool}")
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


def _speak(args: argparse.Namespace) -> CliResult:
    text = " ".join(args.text).strip()
    if (args.clipboard or args.selection) and text:
        return _usage("pass text or one of --clipboard or --selection")
    if args.clipboard:
        source = "clipboard"
        shown = ""
    elif args.selection:
        source = "selection"
        shown = ""
    elif text:
        source = "text"
        shown = f"text: {text}"
    else:
        return _usage("speak needs text, --clipboard, or --selection")
    lines = [
        "digivoice speak is not implemented yet.",
        "PR2 will speak text with Piper and append a history entry.",
        f"source: {source}",
    ]
    if shown:
        lines.append(shown)
    lines.append("No audio was played.")
    lines.append("")
    return _stub("\n".join(lines))


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
        return _speak(args)
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
