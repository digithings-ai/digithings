"""digivoice command line. doctor is live; dict, speak, and history are stubs."""

from __future__ import annotations

import argparse
import os
import sys
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import NoReturn

from digivoice.doctor import doctor_checks, render_doctor
from digivoice.models import CliResult
from digivoice.paths import DEFAULT_MODEL, resolve_paths
from digivoice.probe import CommandProbe, real_probe


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

    dictate = sub.add_parser("dict", help="Record and transcribe (stub until PR1)")
    mode = dictate.add_mutually_exclusive_group()
    mode.add_argument("--hold", action="store_true", help="Hold-to-talk")
    mode.add_argument("--toggle", action="store_true", help="Toggle recording")

    speak = sub.add_parser("speak", help="Speak text with Piper (stub until PR2)")
    source = speak.add_mutually_exclusive_group()
    source.add_argument("--clipboard", action="store_true", help="Read the clipboard")
    source.add_argument("--selection", action="store_true", help="Read the selection")
    speak.add_argument("text", nargs="*", help="Text to speak")

    history = sub.add_parser("history", help="Show the history file (search lands in PR1)")
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


def _dict(args: argparse.Namespace) -> CliResult:
    if args.hold:
        mode = "hold"
    elif args.toggle:
        mode = "toggle"
    else:
        mode = "default"
    return _stub(
        "\n".join(
            [
                "digivoice dict is not implemented yet.",
                "PR1 will record the microphone, run whisper-cli, print the transcript,",
                "paste it into the focused app, and append a history entry.",
                f"mode: {mode}",
                "No audio was captured.",
                "",
            ]
        )
    )


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
    paths = resolve_paths(runtime.platform, runtime.home, runtime.env)
    lines = [
        "digivoice history is a stub until PR1 appends JSONL entries.",
        f"file: {paths.history_file}",
    ]
    if args.last is not None:
        lines.append(f"--last {args.last} will apply once entries exist.")
    if args.grep is not None:
        lines.append(f"--grep {args.grep} will apply once entries exist.")
    lines.append("")
    return CliResult(code=0, stdout="\n".join(lines), stderr="")


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
        return _dict(args)
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
    )
    result = run(argv, runtime)
    if result.stdout:
        sys.stdout.write(result.stdout)
    if result.stderr:
        sys.stderr.write(result.stderr)
    return result.code
