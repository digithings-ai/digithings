#!/usr/bin/env python3
"""Frontend canon guard (#1404, part of #1399).

Keeps every frontend on the digiweb design canon after the 2026-07 migration:
token-backed Tailwind utilities only — no raw palette utilities, no legacy
vocabulary, no color literals in component code.

Checks (git-tracked files under frontend/ only):
  1. Raw Tailwind palette utilities (``bg-zinc-900``, ``text-emerald-400`` …)
     in .tsx/.jsx/.ts — the canon utilities are token-backed (``text-ink``,
     ``bg-surface``, ``text-up`` …) via the @theme inline bridge.
  2. Pre-canon vocabulary (``text-text-primary``, ``fin-green`` …) anywhere.
  3. Hex / rgb() color literals in .tsx/.ts component code. CSS files are NOT
     scanned for literals: the migrate-vs-leave rule sanctions art, masks and
     print pins there, each carrying a token-naming comment.
  4. Family census (#1421): a NEW app-local component-class family (vs the
     committed ``frontend_class_families.json`` baseline) means UI was built
     app-locally instead of promoted through the reference — pages assemble
     from shared primitives.

Escapes:
  * a line containing ``canon-allow`` (with a reason!) is skipped;
  * ALLOWLIST files are sanctioned literal homes (chart palettes, tenant
    embed accents, SSR meta colors);
  * test files are skipped — hygiene tests assert on the banned strings.

Usage: check_frontend_canon.py [--warn]   (--warn reports but exits 0)
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Sanctioned homes for concrete color values.
ALLOWLIST = {
    "frontend/olympus/lib/chart-colors.ts",  # categorical/benchmark chart hues
    "frontend/digichat/src/app/embed/page.tsx",  # tenant embed accent overrides
    "frontend/digiweb/web/src/components/ThemeProvider.tsx",  # SSR theme-color meta
    # Canvas scenes compose runtime colors from token-derived channels
    # (migrate-vs-leave: canvas art stays concrete).
    "frontend/digiquant-web/components/landing/AmbientMesh.tsx",
    "frontend/digiquant-web/components/landing/HeroMesh.tsx",
    "frontend/digiquant-web/components/landing/HeroGraph.tsx",
    "frontend/digithings-web/components/landing/HeroMesh.tsx",
    "frontend/digithings-web/components/landing/HeroGraph.tsx",
    # Reference-app livery chooser: a deliberate concrete swatch table
    # mirroring tokens.css module accents.
    "frontend/digiweb/reference/components/livery-store.ts",
    "frontend/digiweb/reference/components/livery-switcher.tsx",
}

TEST_FILE = re.compile(r"(\.test\.|\.spec\.|/__tests__/|/test/)")

# 1. Raw palette utilities: any variant prefix chain, any Tailwind color
#    family with a numeric shade. Token-backed utilities never match (no
#    numeric shade suffix on ink/surface/hair/accent/up/down/warn/term-*).
#    An optional side/offset segment may sit between the base prefix and the
#    family — directional borders (``border-t-red-500``), ring offsets
#    (``ring-offset-slate-900``), divide axes (``divide-x-blue-600``). The
#    trailing numeric shade is what makes a match, so token utilities (no
#    shade) still never match regardless of the segment.
PALETTE_FAMILIES = (
    "zinc|slate|gray|neutral|stone|red|orange|amber|yellow|lime|green|emerald"
    "|teal|cyan|sky|blue|indigo|violet|purple|fuchsia|pink|rose"
)
SIDE_OFFSET = "t|b|l|r|x|y|s|e|offset"
RAW_UTILITY = re.compile(
    rf"[\"'`\s:\]](?:[a-z-]+:)*"
    rf"(?:text|bg|border|divide|ring|outline|fill|stroke|from|via|to"
    rf"|placeholder|decoration|accent|caret|shadow)"
    rf"-(?:(?:{SIDE_OFFSET})-)?(?:{PALETTE_FAMILIES})-\d{{2,3}}(?:/\d{{1,3}})?\b"
)

# 2. Pre-canon vocabulary (olympus pre-#1402 bridge + fin-* semantics).
LEGACY_VOCAB = re.compile(
    r"\b(?:(?:text|bg|border|divide)-(?:text|bg|border)-(?:primary|secondary"
    r"|muted|subtle|glow|glass)|(?:text|bg|border|stroke|fill)-fin-(?:green"
    r"|red|amber|blue|purple)|var\(--color-(?:text|bg|border|fin)-[a-z-]+\))"
)

# 3. Color literals in component code (hex or rgb/rgba/hsl calls). The hex
#    form must contain at least one letter — pure-digit matches are near
#    always GitHub issue refs (#1215) in comments or strings, and every hue
#    in the canon palette carries a letter.
COLOR_LITERAL = re.compile(
    r"(?:#(?=[0-9a-fA-F]{3,8}\b)[0-9]*[a-fA-F][0-9a-fA-F]*\b|\brgba?\(|\bhsla?\()"
)

UTILITY_EXTS = {".tsx", ".jsx", ".ts"}
VOCAB_EXTS = UTILITY_EXTS | {".css"}
LITERAL_EXTS = {".tsx", ".ts"}

COMMENT_LINE = re.compile(r"^\s*(?://|\*|/\*|\{/\*)")
TRAILING_COMMENT = re.compile(r"(?<![:\w])//.*$")  # not ://  (URLs)
BLOCK_COMMENT = re.compile(r"/\*.*?\*/")


def literal_scan_text(line: str) -> str:
    """The color-literal check ignores comments, var(--token) lines (token
    fallbacks like ``var(--down, #e0654b)`` are the sanctioned pattern), and
    template-composed canvas colors (``rgba(${chan},…)``)."""
    if (
        COMMENT_LINE.match(line)
        or "var(--" in line
        or "(${" in line
        # any quoted token name on the line: cssVar("--ink", "#ECEEF0") /
        # getPropertyValue("--bg") fallbacks are the sanctioned SSR pattern
        or re.search(r"[\"'`]--[a-z]", line)
    ):
        return ""
    return TRAILING_COMMENT.sub("", BLOCK_COMMENT.sub("", line))


FAMILY_BASELINE = REPO / "scripts" / "frontend_class_families.json"
# Apps under the family-census ratchet (#1421). digiweb (reference + shared
# packages) is exempt — it is WHERE new families are supposed to be born.
CENSUS_APPS = ("digithings-web", "digiquant-web", "olympus", "digichat", "digichat-ui")
CLASS_DEF = re.compile(r"^\.([a-z][a-z0-9]+)(?:-|\s|:|\.|,|\{)", re.M)


def family_census_findings(files: list[str]) -> list[tuple[str, int, str, str]]:
    """Ratchet v2 (#1421): pages assemble from shared primitives — an app
    growing a NEW component-class family means someone built UI app-locally
    instead of promoting it through the reference (MIGRATION.md playbook)."""
    baseline = json.loads(FAMILY_BASELINE.read_text())
    findings: list[tuple[str, int, str, str]] = []
    for app in CENSUS_APPS:
        allowed = set(baseline.get(app, []))
        for rel in files:
            if not rel.startswith(f"frontend/{app}/") or not rel.endswith(".css"):
                continue
            text = (REPO / rel).read_text(encoding="utf-8")
            for m in CLASS_DEF.finditer(text):
                fam = m.group(1)
                if fam not in allowed:
                    lineno = text.count("\n", 0, m.start()) + 1
                    findings.append(
                        (
                            rel,
                            lineno,
                            "new-component-family",
                            f".{fam}-* is not in {app}'s baseline — promote via the "
                            f"reference (MIGRATION.md) or extend {FAMILY_BASELINE.name}",
                        )
                    )
                    allowed.add(fam)  # one finding per new family per app
    return findings


def tracked_frontend_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files", "frontend"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def main() -> int:
    warn_only = "--warn" in sys.argv[1:]
    tracked = tracked_frontend_files()
    findings: list[tuple[str, int, str, str]] = list(family_census_findings(tracked))

    for rel in tracked:
        ext = Path(rel).suffix
        if ext not in VOCAB_EXTS or TEST_FILE.search(rel):
            continue
        try:
            text = (REPO / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        allowlisted = rel in ALLOWLIST
        for lineno, line in enumerate(text.splitlines(), start=1):
            if "canon-allow" in line:
                continue
            if ext in UTILITY_EXTS and RAW_UTILITY.search(line):
                findings.append((rel, lineno, "raw-palette-utility", line.strip()))
            if LEGACY_VOCAB.search(line):
                findings.append((rel, lineno, "legacy-vocabulary", line.strip()))
            if (
                ext in LITERAL_EXTS
                and not allowlisted
                and COLOR_LITERAL.search(literal_scan_text(line))
            ):
                findings.append((rel, lineno, "color-literal", line.strip()))

    if findings:
        print(f"frontend canon guard: {len(findings)} finding(s)\n")
        for rel, lineno, kind, snippet in findings[:100]:
            print(f"  {rel}:{lineno}  [{kind}]  {snippet[:110]}")
        if len(findings) > 100:
            print(f"  … and {len(findings) - 100} more")
        print(
            "\nUse token-backed utilities (text-ink, bg-surface, text-up …) or add"
            "\na `canon-allow: <reason>` comment / ALLOWLIST entry for sanctioned"
            "\nliterals. Playbook: frontend/digiweb/MIGRATION.md"
        )
        return 0 if warn_only else 1

    print("frontend canon guard: clean")
    return 0


if __name__ == "__main__":
    sys.exit(main())
