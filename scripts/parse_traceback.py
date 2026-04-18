#!/usr/bin/env python3
"""
parse_traceback.py — Parse a Python stack trace and identify the DigiThings component.

Usage:
  python3 scripts/parse_traceback.py                  # read from stdin
  python3 scripts/parse_traceback.py --input file.txt # read from file
  python3 scripts/parse_traceback.py --format json    # JSON output
  echo "Traceback..." | python3 scripts/parse_traceback.py

Output (text):
  Component: digisearch | File: digisearch/src/digisearch/ingest.py:42 | Error: ValueError: ...

Output (json):
  {"component": "digisearch", "file": "digisearch/src/digisearch/ingest.py",
   "line": 42, "error_type": "ValueError", "message": "...", "full_trace": "..."}

Exit code: always 0 (informational tool)
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Map source path prefixes → component names (order matters: most specific first)
COMPONENT_PATHS: list[tuple[str, str]] = [
    ("digigraph/src/digigraph", "digigraph"),
    ("digiquant/src/digiquant", "digiquant"),
    ("digisearch/src/digisearch", "digisearch"),
    ("digismith/src/digismith", "digismith"),
    ("digiclaw/", "digiclaw"),
    ("digibase/src/digibase", "digibase"),
    ("digikey/src/digikey", "digikey"),
    ("digichat/", "digichat"),
    ("digigraph/", "digigraph"),
    ("digiquant/", "digiquant"),
    ("digisearch/", "digisearch"),
    ("digismith/", "digismith"),
    ("digibase/", "digibase"),
    ("digikey/", "digikey"),
    ("scripts/", "scripts"),
]


def identify_component(file_path: str) -> str:
    """Map a file path to a DigiThings component name."""
    # Normalize: strip leading slashes and repo root prefix
    path = file_path.replace("\\", "/")
    # Try to strip repo root so we get relative path
    try:
        path = str(Path(file_path).relative_to(REPO_ROOT))
    except ValueError:
        pass  # file_path may already be relative

    for prefix, component in COMPONENT_PATHS:
        if path.startswith(prefix) or f"/{prefix}" in path:
            return component

    return "unknown"


def parse_traceback(text: str) -> dict | None:
    """
    Parse a Python traceback string and return structured info.
    Returns None if no traceback is detected.
    """
    if "Traceback (most recent call last):" not in text and \
       not re.search(r'\bError\b.*:\s*.+', text):
        return None

    # Extract all frame lines: '  File "path", line N, in func'
    frame_pattern = re.compile(r'File "([^"]+)", line (\d+), in (\S+)')
    frames = frame_pattern.findall(text)

    if not frames:
        # No standard frames — try to extract error type/message only
        error_match = re.search(r'^(\w+(?:\.\w+)*Error|\w+Exception|KeyboardInterrupt):\s*(.*)$',
                                 text, re.MULTILINE)
        if error_match:
            return {
                "component": "unknown",
                "file": "",
                "line": 0,
                "error_type": error_match.group(1),
                "message": error_match.group(2).strip(),
                "full_trace": text.strip(),
            }
        return None

    # Last frame is the most relevant
    last_file, last_line, _ = frames[-1]

    # Error type and message: last line of the traceback
    lines = [l.rstrip() for l in text.splitlines() if l.strip()]
    error_line = lines[-1] if lines else ""
    error_type = "UnknownError"
    error_msg = error_line

    error_match = re.match(r'^(\w+(?:\.\w+)*(?:Error|Exception|Warning|Interrupt)):\s*(.*)', error_line)
    if error_match:
        error_type = error_match.group(1)
        error_msg = error_match.group(2).strip()
    elif ":" in error_line:
        parts = error_line.split(":", 1)
        error_type = parts[0].strip()
        error_msg = parts[1].strip()

    component = identify_component(last_file)

    # Make file path relative if possible
    try:
        rel_file = str(Path(last_file).relative_to(REPO_ROOT))
    except ValueError:
        rel_file = last_file

    return {
        "component": component,
        "file": rel_file,
        "line": int(last_line),
        "error_type": error_type,
        "message": error_msg,
        "full_trace": text.strip(),
    }


def main() -> int:
    parser = argparse.ArgumentParser(
        description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("--input", "-i", metavar="FILE",
                        help="Read traceback from file (default: stdin)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Output format (default: text)")
    args = parser.parse_args()

    if args.input:
        try:
            text = Path(args.input).read_text()
        except FileNotFoundError:
            print(f"ERROR: file not found: {args.input}", file=sys.stderr)
            return 0
    else:
        if sys.stdin.isatty():
            print("Paste traceback (end with Ctrl+D):", file=sys.stderr)
        text = sys.stdin.read()

    result = parse_traceback(text)

    if result is None:
        if args.format == "json":
            print(json.dumps({"error": "No traceback detected"}))
        else:
            print("No traceback detected.")
        return 0

    if args.format == "json":
        # Don't include full_trace in json by default — it's large
        output = {k: v for k, v in result.items() if k != "full_trace"}
        print(json.dumps(output, indent=2))
    else:
        loc = f"{result['file']}:{result['line']}" if result["file"] else "(unknown location)"
        print(f"Component: {result['component']} | File: {loc} | "
              f"Error: {result['error_type']}: {result['message']}")
        print()
        print("Next steps:")
        if result["component"] != "unknown":
            print(f"  1. Read {result['component']}/AGENTS.md")
            print(f"  2. Open {loc} at line {result['line']}")
        print(f"  3. Create issue: scripts/create_issue.sh "
              f"--component {result['component']} "
              f"--type fix "
              f"--title \"fix({result['component']}): {result['error_type']} at {loc}\"")

    return 0


if __name__ == "__main__":
    sys.exit(main())
