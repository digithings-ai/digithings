"""Mutation harness for DIG-1079's Art. 9 screen.

Not part of the deliverable. Delete after use.

Discipline baked in:
  * mutants are (name, [(old, new), ...]) passed as DATA, never interpolated
  * each rewrite asserts it applied exactly once AND changed the bytes
  * restore is `git checkout --` (git is authoritative), inside `finally`
  * the file is byte-compared to the original after EVERY mutant
  * rc==1 (tests ran, assertions failed) is a kill; rc==2 is a PARSE ERROR
    and is reported separately, never counted as a kill
  * every mutant runs against the WHOLE test file, so a one-node death is
    distinguishable from a selector artefact
"""

from __future__ import annotations

import pathlib
import re
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parent
TARGET = REPO / "digisearch/src/digisearch/pipeline/ingest.py"
REL = "digisearch/src/digisearch/pipeline/ingest.py"
TESTS = "tests/ds/test_art9_index_chunks.py"
PY = str(REPO / ".venv/bin/python")

PAYLOAD_OLD = (
    "    result = screen_request(\n"
    '        [{"content": c.content, "doc_id": c.doc_id, "metadata": c.metadata} for c in chunks]\n'
    "    )"
)
CALL_OLD = "    _screen_art9(index_name, chunks)\n\n    provider = embedding_provider"

MUTANTS: list[tuple[str, list[tuple[str, str]]]] = [
    # the gate simply does not exist
    ("M1_no_screen_call", [(CALL_OLD, "    provider = embedding_provider")]),
    # revision-1 placement: screen AFTER apply_embeddings (what the brief forbids)
    (
        "M2_screen_after_apply_embeddings",
        [
            (CALL_OLD, "    provider = embedding_provider"),
            (
                "    if provider is not None:\n        apply_embeddings(chunks, provider)\n",
                "    if provider is not None:\n        apply_embeddings(chunks, provider)\n"
                "    _screen_art9(index_name, chunks)\n",
            ),
        ],
    ),
    # drop metadata -> field-name coverage lost, content still screened
    ("M3_content_only_payload", [(PAYLOAD_OLD, "    result = screen_request([c.content for c in chunks])")]),
    # fail open
    (
        "M4_fail_open",
        [('    if result.decision == "allow":\n        return', '    if result.decision != "allow":\n        return')],
    ),
    # hidden bypass switch
    (
        "M5_exception_ref_bypass",
        [(PAYLOAD_OLD, PAYLOAD_OLD[:-1] + ',\n        exception_ref="manual",\n    )')],
    ),
    # stable error code lost
    (
        "M6_wrong_error_code",
        [('ART9_REFUSED_CODE = "art9_special_category"', 'ART9_REFUSED_CODE = "ingest_failed"')],
    ),
    # 422 -> 503 is the "backend is down" mistake
    ("M7_wrong_http_status", [("ART9_REFUSED_STATUS = 422", "ART9_REFUSED_STATUS = 503")]),
    # refusal reason dropped from the message
    (
        "M8_reason_dropped_from_message",
        [
            (
                'f"index {index_name!r} refused: chunks carry Art. 9 special-category data ({result.reason})"',
                'f"index {index_name!r} refused: chunks carry Art. 9 special-category data"',
            )
        ],
    ),
    # empty batch refuses (guards nothing, breaks every empty-batch caller)
    (
        "M9_empty_batch_refuses",
        [("    if not chunks:\n        return\n\n    result = screen_request(", "    result = screen_request(")],
    ),
]


def run_tests() -> tuple[int, list[str], str]:
    proc = subprocess.run(
        [PY, "-m", "pytest", TESTS, "-q", "--no-header", "--tb=no", "-p", "no:cacheprovider"],
        cwd=REPO,
        capture_output=True,
        text=True,
    )
    failed = sorted(set(re.findall(r"^(?:FAILED|ERROR) (\S+)", proc.stdout, re.M)))
    tail = proc.stdout.strip().splitlines()[-1] if proc.stdout.strip() else "(no output)"
    return proc.returncode, failed, tail


def restore(original: bytes) -> None:
    subprocess.run(["git", "checkout", "--", REL], cwd=REPO, check=True)
    after = TARGET.read_bytes()
    if after != original:
        raise SystemExit(f"FATAL: restore did not return {REL} to its original bytes")


def main() -> int:
    original = TARGET.read_bytes()
    results: list[tuple[str, str, list[str]]] = []

    # control run first: on the UNMUTATED tree the suite must be green, else every
    # later reading is meaningless.
    rc, failed, tail = run_tests()
    print(f"CONTROL  rc={rc}  {tail}", flush=True)
    if rc != 0:
        print(f"FATAL: control is not green; aborted. failures={failed}", flush=True)
        return 2

    for name, edits in MUTANTS:
        try:
            source = original.decode()
            for old, new in edits:
                count = source.count(old)
                if count != 1:
                    raise SystemExit(
                        f"FATAL: {name} anchor occurs {count} times, not 1: {old[:70]!r}"
                    )
                source = source.replace(old, new)
            if source.encode() == original:
                raise SystemExit(f"FATAL: {name} produced no byte change")
            TARGET.write_text(source)
            if TARGET.read_bytes() == original:
                raise SystemExit(f"FATAL: {name} write did not land")
            rc, failed, tail = run_tests()
            if rc == 0:
                verdict = "SURVIVED"
            elif rc == 1:
                verdict = "killed"
            else:
                verdict = f"PARSE-ERROR rc={rc}"
            results.append((name, verdict, failed))
            print(f"{verdict:<16} rc={rc}  {name}  -> {len(failed)} node(s)", flush=True)
            for node in failed:
                print(f"                   killed-by: {node}", flush=True)
            if verdict != "killed" and tail:
                print(f"                   tail: {tail}", flush=True)
        finally:
            restore(original)

    survived = [n for n, v, _ in results if v != "killed"]
    print("\n=== SUMMARY ===", flush=True)
    print(f"mutants: {len(results)}  killed: {len(results) - len(survived)}", flush=True)
    print(f"survived/other: {survived}", flush=True)
    print(f"tree restored byte-identical: {TARGET.read_bytes() == original}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())