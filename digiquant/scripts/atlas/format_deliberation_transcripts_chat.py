#!/usr/bin/env python3
"""
format_deliberation_transcripts_chat.py

Rewrite Supabase `documents.content` for deliberation transcripts into a consistent,
chat-style markdown layout (PM vs Analyst, rounds, and a Decision block) WITHOUT
changing the underlying facts.

Targets:
  documents.document_key like 'deliberation-transcript/YYYY-MM-DD/*.json'

Notes:
- We preserve any existing content but normalize speaker/round formatting.
- Idempotent: running multiple times should produce the same output.

Usage:
  python3 scripts/format_deliberation_transcripts_chat.py --start YYYY-MM-DD --end YYYY-MM-DD --apply
  python3 scripts/format_deliberation_transcripts_chat.py --start YYYY-MM-DD --end YYYY-MM-DD --dry-run

Env: SUPABASE_URL, SUPABASE_SERVICE_KEY (config/supabase.env)
"""

from __future__ import annotations

import argparse
import os
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

try:
    from supabase import create_client  # type: ignore
except Exception as e:  # pragma: no cover
    raise SystemExit(f"Install supabase: python3 -m pip install supabase ({e})")

try:
    from dotenv import load_dotenv  # type: ignore

    load_dotenv(Path(__file__).parent.parent / "config" / "supabase.env")
    load_dotenv()
except Exception:
    pass


def _sb():
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_KEY")
    if not url or not key:
        raise SystemExit("SUPABASE_URL and SUPABASE_SERVICE_KEY required")
    return create_client(url, key)


_RE_HEADER = re.compile(r"^#\s*Deliberation Transcript\s+—\s*(?P<ticker>[A-Z0-9._-]+)\s*\|\s*(?P<date>\d{4}-\d{2}-\d{2})\s*$")
_RE_META_LINE = re.compile(r"^\*\*Meta:\*\*.*$", re.I)
_RE_DATE_ROUNDS_OUTCOME = re.compile(
    r"^\*\*Date:\*\*\s*(?P<date>\d{4}-\d{2}-\d{2})\s*\|\s*\*\*Rounds:\*\*\s*(?P<rounds>\d+)\s*\|\s*\*\*Outcome:\*\*\s*(?P<outcome>.+?)\s*$"
)
_RE_ROUND_SPEAKER = re.compile(
    r"^(?:(?P<round>Round\s*\d+)\s*[-—]\s*)?(?P<speaker>Analyst|PM)\s*:\s*(?P<msg>.+)$",
    re.I,
)
_RE_ROUND_PREFIX = re.compile(r"^(Round\s*\d+)\s*[-—]\s*(?P<speaker>Analyst|PM)\s*:\s*(?P<msg>.+)$", re.I)
_RE_PM_CONVERGED = re.compile(r"\bCONVERGED\b", re.I)
_RE_PM_INLINE = re.compile(r"\bPM\s*:\s*", re.I)


@dataclass(frozen=True)
class ParsedHeader:
    ticker: str
    date: str
    rounds: Optional[int]
    outcome: Optional[str]


def _strip_fence_noise(lines: list[str]) -> list[str]:
    # Some legacy content contains leading/trailing blank or separators; keep it simple.
    while lines and not lines[0].strip():
        lines.pop(0)
    while lines and not lines[-1].strip():
        lines.pop()
    return lines


def _parse_existing_header(lines: list[str]) -> Optional[ParsedHeader]:
    if not lines:
        return None
    m = _RE_HEADER.match(lines[0].strip())
    if not m:
        return None
    ticker = m.group("ticker").strip().upper()
    date = m.group("date").strip()
    rounds: Optional[int] = None
    outcome: Optional[str] = None
    if len(lines) > 2:
        m2 = _RE_DATE_ROUNDS_OUTCOME.match(lines[2].strip())
        if m2:
            try:
                rounds = int(m2.group("rounds"))
            except Exception:
                rounds = None
            outcome = m2.group("outcome").strip()
    return ParsedHeader(ticker=ticker, date=date, rounds=rounds, outcome=outcome)


def _extract_meta_kv(lines: Iterable[str]) -> tuple[Optional[bool], Optional[int], Optional[str]]:
    converged: Optional[bool] = None
    rounds: Optional[int] = None
    final_action: Optional[str] = None
    for ln in lines:
        if not ln.lower().startswith("**meta:**"):
            continue
        low = ln.lower()
        if "converged=true" in low:
            converged = True
        elif "converged=false" in low:
            converged = False
        rm = re.search(r"rounds\s*=\s*(\d+)", low)
        if rm:
            try:
                rounds = int(rm.group(1))
            except Exception:
                pass
        am = re.search(r"final_action\s*=\s*([a-z_]+)", low)
        if am:
            final_action = am.group(1).upper()
    return converged, rounds, final_action


def _format_chat_markdown(raw: str, fallback_ticker: str, fallback_date: str) -> str:
    lines = raw.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    lines = _strip_fence_noise(lines)

    hdr = _parse_existing_header(lines)
    ticker = hdr.ticker if hdr else fallback_ticker
    date = hdr.date if hdr else fallback_date

    # Remove existing header blocks if present (we'll rebuild).
    if hdr:
        # common structure:
        # 0: header
        # 1: blank
        # 2: date|rounds|outcome line
        # 3: blank
        # 4: ---
        # 5: blank
        cut = 0
        for i, ln in enumerate(lines[:12]):
            if ln.strip() == "---":
                cut = i + 1
                break
        if cut:
            lines = lines[cut:]
        else:
            lines = lines[3:]
        lines = _strip_fence_noise(lines)

    # Drop trailing meta line; we'll rebuild a Decision block.
    body_lines: list[str] = []
    for ln in lines:
        s0 = ln.strip()
        if _RE_META_LINE.match(s0):
            continue
        # If a prior run already produced markdown, strip common markdown-only
        # artifacts so we can re-parse idempotently.
        # - remove blockquote markers
        while s0.startswith(">"):
            s0 = s0[1:].lstrip()
        # - remove emphasis markers (we only need the text)
        s0 = s0.replace("**", "")
        # - skip structural headings / separators / decision bullets
        low = s0.lower().strip()
        if not low:
            continue
        if low == "---" or low.startswith("# "):
            continue
        if low.startswith("## "):
            continue
        if low in ("transcript", "decision"):
            continue
        if low.startswith("- "):
            continue
        body_lines.append(s0)

    # Parse conversation into speaker blocks.
    blocks: list[tuple[str, Optional[str], str]] = []  # (speaker, round_label, msg)
    current_round: Optional[str] = None
    pending_speaker: Optional[str] = None

    def _append_block(speaker: str, round_label: Optional[str], msg: str) -> None:
        m = (msg or "").strip()
        if not m:
            return
        blocks.append((speaker, round_label, m))

    def _split_inline_pm(msg: str) -> tuple[str, Optional[str]]:
        """
        Some legacy transcripts embed both voices in one line, e.g.
        "BIL ... Hold. PM: CONVERGED: HOLD 40%."
        Return (analyst_msg, pm_msg|None).
        """
        parts = _RE_PM_INLINE.split(msg, maxsplit=1)
        if len(parts) <= 1:
            return msg, None
        a = parts[0].strip()
        p = parts[1].strip()
        return a, p or None
    for ln in body_lines:
        s = (ln or "").strip()
        if not s:
            continue
        if s.lower().startswith("meta:"):
            continue

        # Handle 2-line speaker blocks like:
        # "ANALYST:" then next line message.
        if re.fullmatch(r"(analyst|pm)\s*:\s*", s, flags=re.I):
            pending_speaker = s.split(":", 1)[0].strip().upper()
            continue
        if pending_speaker:
            speaker = pending_speaker
            pending_speaker = None
            if speaker == "ANALYST":
                a_msg, pm_msg = _split_inline_pm(s)
                _append_block("ANALYST", current_round, a_msg)
                if pm_msg:
                    _append_block("PM", current_round, pm_msg)
            else:
                _append_block(speaker, current_round, s)
            continue
        # normalize "Round N — Speaker:" forms
        m = _RE_ROUND_PREFIX.match(s)
        if m:
            current_round = m.group(1).replace(" ", "")
            speaker = m.group("speaker").upper()
            msg = m.group("msg").strip()
            if speaker == "ANALYST":
                a_msg, pm_msg = _split_inline_pm(msg)
                _append_block("ANALYST", current_round, a_msg)
                if pm_msg:
                    _append_block("PM", current_round, pm_msg)
            else:
                _append_block(speaker, current_round, msg)
            continue
        m2 = _RE_ROUND_SPEAKER.match(s)
        if m2:
            round_part = m2.group("round")
            if round_part:
                current_round = round_part.replace(" ", "")
            speaker = m2.group("speaker").upper()
            msg = m2.group("msg").strip()
            if speaker == "ANALYST":
                a_msg, pm_msg = _split_inline_pm(msg)
                _append_block("ANALYST", current_round, a_msg)
                if pm_msg:
                    _append_block("PM", current_round, pm_msg)
            elif speaker == "PM":
                _append_block("PM", current_round, msg)
            else:
                _append_block(speaker, current_round, msg)
            continue
        # Fallback: keep as narrator line.
        # Also catch bare "PM:" lines that aren't in the expected regex form.
        if s.lower().startswith("pm:"):
            _append_block("PM", current_round, s.split(":", 1)[1].strip())
        else:
            _append_block("NOTE", None, s)

    converged, meta_rounds, meta_action = _extract_meta_kv(lines)
    outcome = hdr.outcome if hdr and hdr.outcome else (meta_action or "—")
    rounds_val = hdr.rounds if hdr and hdr.rounds else meta_rounds

    out: list[str] = []
    out.append(f"# Deliberation Transcript — {ticker} | {date}")
    out.append("")
    bits = [f"**Date:** {date}"]
    if rounds_val is not None:
        bits.append(f"**Rounds:** {rounds_val}")
    if outcome:
        bits.append(f"**Outcome:** {outcome}")
    out.append(" | ".join(bits))
    out.append("")
    out.append("---")
    out.append("")
    out.append("## Transcript")
    out.append("")

    for speaker, round_label, msg in blocks:
        if speaker == "NOTE":
            out.append(f"> {msg}")
            out.append("")
            continue
        label = speaker
        if round_label:
            label = f"{speaker} ({round_label})"
        out.append(f"**{label}:**")
        out.append(msg)
        out.append("")

    out.append("## Decision")
    out.append("")
    out.append(f"- **Action**: {outcome or '—'}")
    if converged is not None:
        out.append(f"- **Converged**: {'Yes' if converged else 'No'}")
    if rounds_val is not None:
        out.append(f"- **Rounds**: {rounds_val}")
    out.append("")
    return "\n".join(out).rstrip() + "\n"


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", required=True)
    ap.add_argument("--end", required=True)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if args.dry_run == args.apply:
        raise SystemExit("Choose exactly one of --dry-run or --apply")

    sb = _sb()
    start = args.start
    end = args.end

    # Pull keys + minimal payload for ticker/date and existing content.
    rows = (
        sb.table("documents")
        .select("id,date,document_key,content,payload")
        .gte("date", start)
        .lte("date", end)
        .ilike("document_key", "deliberation-transcript/%")
        .execute()
        .data
        or []
    )

    changed = 0
    for r in rows:
        doc_id = r.get("id")
        d = str(r.get("date") or "")[:10]
        key = str(r.get("document_key") or "")
        content = r.get("content") or ""
        payload = r.get("payload") if isinstance(r.get("payload"), dict) else {}
        ticker = str(payload.get("ticker") or key.split("/")[-1].split(".")[0]).upper()
        if not d or not key or not doc_id:
            continue
        if not content.strip():
            # Nothing to format.
            continue
        new_md = _format_chat_markdown(content, fallback_ticker=ticker, fallback_date=d)
        if new_md.strip() == content.strip():
            continue
        changed += 1
        if args.dry_run:
            print(f"[dry-run] would update {d} {key} ({len(content)}→{len(new_md)} chars)")
            continue
        sb.table("documents").update({"content": new_md}).eq("id", doc_id).execute()
        print(f"✅ updated {d} {key}")

    print(f"Done. {'Would change' if args.dry_run else 'Changed'} {changed} row(s).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

