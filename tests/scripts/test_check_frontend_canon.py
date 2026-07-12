"""Unit tests for scripts/check_frontend_canon.py (#1434).

The frontend canon guard keeps every frontend on the digiweb design canon:
token-backed Tailwind utilities only — no raw palette utilities, no legacy
vocabulary, no color literals in component code — plus a family-census ratchet
that flags new app-local component-class families.

These are regression tests for that 207-line guard, which previously shipped
with no coverage. They lock in, in particular, the broadened RAW_UTILITY regex
(#1434) that now catches directional-border / ring-offset raw palette
utilities (``border-t-red-500``, ``ring-offset-slate-900``) that used to slip
through. Fixtures live under tmp_path with module globals monkeypatched — the
real tree is never mutated.
"""

from __future__ import annotations

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
_SCRIPT = REPO_ROOT / "scripts" / "check_frontend_canon.py"

pytestmark = pytest.mark.unit


def _load_module():
    spec = importlib.util.spec_from_file_location("check_frontend_canon", _SCRIPT)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)  # type: ignore[union-attr]
    return mod


@pytest.fixture(scope="module")
def mod():
    return _load_module()


# ── 1. Raw palette utilities (incl. the directional/offset gap fixed in #1434) ─


@pytest.mark.parametrize(
    "utility",
    [
        # Plain palette utilities (always caught).
        "bg-zinc-900",
        "text-emerald-400",
        "bg-red-500/50",
        # Directional borders / ring offsets / divide axes — the #1434 gap:
        # an optional side/offset segment sits between prefix and family.
        "border-t-red-500",
        "border-b-blue-600",
        "border-x-emerald-400",
        "border-s-stone-700",
        "border-e-teal-300",
        "border-y-amber-200",
        "ring-offset-slate-900",
        "divide-x-blue-600",
        # Variant chains still prefix-match.
        "hover:border-t-red-500",
        "dark:md:bg-zinc-900",
    ],
)
def test_raw_utility_flags_palette(mod, utility: str) -> None:
    # Utilities appear inside a className string — the regex requires a
    # leading quote/space/colon/bracket boundary.
    assert mod.RAW_UTILITY.search(f'className="{utility}"'), utility


@pytest.mark.parametrize(
    "utility",
    [
        # Token-backed utilities carry no numeric shade — must never match,
        # even with the broadened side/offset segment.
        "text-ink",
        "bg-surface",
        "border-hair",
        "text-up",
        "text-down",
        "text-term-green",
        # Width/spacing utilities that share the side segment but no family.
        "border-x-2",
        "divide-y-2",
        "border-t",
        "rounded-t-lg",
        "inset-x-0",
    ],
)
def test_raw_utility_ignores_token_utilities(mod, utility: str) -> None:
    assert not mod.RAW_UTILITY.search(f'className="{utility}"'), utility


# ── 2. Legacy (pre-canon) vocabulary ───────────────────────────────────────────


@pytest.mark.parametrize(
    "snippet",
    [
        "text-text-primary",
        "bg-bg-muted",
        "text-fin-green",
        "stroke-fin-red",
        "var(--color-text-subtle)",
        "var(--color-fin-blue)",
    ],
)
def test_legacy_vocab_flagged(mod, snippet: str) -> None:
    assert mod.LEGACY_VOCAB.search(snippet), snippet


@pytest.mark.parametrize("snippet", ["text-ink", "bg-surface", "var(--ink)", "var(--accent)"])
def test_legacy_vocab_ignores_canon(mod, snippet: str) -> None:
    assert not mod.LEGACY_VOCAB.search(snippet), snippet


# ── 3. Color literals in component code ────────────────────────────────────────


def test_hex_literal_flagged(mod) -> None:
    scanned = mod.literal_scan_text('const brand = "#ff8800";')
    assert mod.COLOR_LITERAL.search(scanned)


def test_rgb_literal_flagged(mod) -> None:
    scanned = mod.literal_scan_text("const shadow = rgba(12, 12, 12, 0.4);")
    assert mod.COLOR_LITERAL.search(scanned)


def test_var_token_fallback_not_flagged(mod) -> None:
    # ``var(--down, #e0654b)`` is the sanctioned token-fallback pattern.
    scanned = mod.literal_scan_text("color: var(--down, #e0654b);")
    assert scanned == ""
    assert not mod.COLOR_LITERAL.search(scanned)


def test_hex_in_comment_not_flagged(mod) -> None:
    assert mod.literal_scan_text("// mirrors --ink #ecEEF0") == ""


def test_issue_ref_not_flagged_as_literal(mod) -> None:
    # Pure-digit ``#1215`` (GitHub issue ref) must not read as a color.
    scanned = mod.literal_scan_text("// see #1215 for context")
    assert not mod.COLOR_LITERAL.search(scanned or "x #1215")


# ── 4. Family census (#1421): a new app-local class family is flagged ──────────


def _write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def test_family_census_flags_new_family(mod, tmp_path, monkeypatch) -> None:
    baseline = tmp_path / "scripts" / "frontend_class_families.json"
    _write(baseline, json.dumps({"digichat-ui": ["msg"]}))
    rel = "frontend/digichat-ui/styles.css"
    _write(
        tmp_path / rel,
        ".msg-bubble { color: red; }\n.widget-shell { display: flex; }\n",
    )
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "FAMILY_BASELINE", baseline)

    findings = mod.family_census_findings([rel])

    kinds = {f[2] for f in findings}
    families = " ".join(f[3] for f in findings)
    assert kinds == {"new-component-family"}
    assert "widget" in families  # the new family
    assert "msg" not in families  # baselined family stays silent


def test_family_census_silent_when_baselined(mod, tmp_path, monkeypatch) -> None:
    baseline = tmp_path / "scripts" / "frontend_class_families.json"
    _write(baseline, json.dumps({"digichat-ui": ["msg", "widget"]}))
    rel = "frontend/digichat-ui/styles.css"
    _write(tmp_path / rel, ".msg-bubble {}\n.widget-shell {}\n")
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "FAMILY_BASELINE", baseline)

    assert mod.family_census_findings([rel]) == []


# ── 5. End-to-end main(): allowlist / canon-allow / var-fallback gating ────────


def test_main_end_to_end(mod, tmp_path, monkeypatch, capsys) -> None:
    baseline = tmp_path / "scripts" / "frontend_class_families.json"
    _write(baseline, json.dumps({"digichat-ui": ["msg"]}))

    bad_tsx = "frontend/digichat/src/bad.tsx"
    _write(
        tmp_path / bad_tsx,
        "\n".join(
            [
                '<div className="bg-zinc-900" />',
                '<div className="border-t-red-500 p-2" />',  # directional regression
                '<span className="text-text-primary" />',  # legacy vocabulary
                'const brand = "#ff8800";',  # color literal
                '<div className="text-ink bg-surface" />',  # sanctioned — no match
                '<div className="bg-rose-600" /> // canon-allow: legacy gradient',
                'const fallback = "var(--down, #e0654b)";',  # sanctioned fallback
            ]
        )
        + "\n",
    )

    # Letter-bearing hexes: pure-digit ``#123456`` reads as an issue ref, not a
    # color, so the allowlist contrast would be vacuous without a letter.
    allow_ts = "frontend/olympus/lib/chart-colors.ts"
    _write(tmp_path / allow_ts, 'export const up = "#12ab56";\n')  # allowlisted home
    other_ts = "frontend/olympus/lib/other.ts"
    _write(tmp_path / other_ts, 'export const x = "#65cd21";\n')  # NOT allowlisted

    census_css = "frontend/digichat-ui/styles.css"
    _write(tmp_path / census_css, ".msg-bubble {}\n.widget-shell {}\n")

    tracked = [bad_tsx, allow_ts, other_ts, census_css]
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "FAMILY_BASELINE", baseline)
    monkeypatch.setattr(mod, "ALLOWLIST", {allow_ts})
    monkeypatch.setattr(mod, "tracked_frontend_files", lambda: tracked)

    rc = mod.main()
    out = capsys.readouterr().out

    assert rc == 1
    # Every finding kind fires.
    assert "[raw-palette-utility]" in out
    assert "border-t-red-500" in out  # directional gap locked in end-to-end
    assert "[legacy-vocabulary]" in out
    assert "[color-literal]" in out
    assert "[new-component-family]" in out
    # Sanctioned patterns do NOT fire.
    assert "rose-600" not in out  # canon-allow line skipped wholesale
    assert "e0654b" not in out  # var(--token, #hex) fallback not a literal
    assert "chart-colors.ts" not in out  # allowlisted literal home
    assert "other.ts" in out  # …but a non-allowlisted literal still fires


def test_main_clean_tree_returns_zero(mod, tmp_path, monkeypatch, capsys) -> None:
    baseline = tmp_path / "scripts" / "frontend_class_families.json"
    _write(baseline, json.dumps({}))
    rel = "frontend/digichat/src/ok.tsx"
    _write(tmp_path / rel, '<div className="text-ink bg-surface border-hair" />\n')
    monkeypatch.setattr(mod, "REPO", tmp_path)
    monkeypatch.setattr(mod, "FAMILY_BASELINE", baseline)
    monkeypatch.setattr(mod, "tracked_frontend_files", lambda: [rel])

    assert mod.main() == 0
    assert "clean" in capsys.readouterr().out
