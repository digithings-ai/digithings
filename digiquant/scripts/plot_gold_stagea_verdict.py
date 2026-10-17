"""Stage-B verdict comparison chart as stdlib-only SVG (#4804, Plan 18 Task 5).

Same 960-wide hand-rolled SVG pattern as plot_gold_stagea_votes.py (no
plotting library in .venv; pip installs forbidden). Reads precomputed
numbers ONLY from existing artifacts (recomputes nothing, runs nothing):
behavior fills from the Task-3 diagnostic tearsheet JSONs, gate means /
beats flags / sens / frontier from the Task-4 gate JSONs. Three panels —
(A) sell fills/yr vs the reselect baseline, (B) mean OOS vs flat AND lump
per vote with a zero line, (C) frontier shapes beating both / 1728.

Output: digiquant/.scratch/gold_pngs/gold_stagea_verdict.svg plus a
public/ copy for the preview server. Stays untracked. No page.tsx entry:
entry is allowed ONLY on BEATS-BOTH, and the verdict here is NEITHER.
"""

import json
import shutil
from datetime import date
from pathlib import Path
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
PUBLIC_STRATEGIES = ROOT.parent / "apps" / "digiquant-web" / "public" / "strategies"
OUT_DIR = ROOT / ".scratch" / "gold_pngs"
PUBLIC_DIR = ROOT.parent / "apps" / "digiquant-web" / "public" / "gold_charts"

W, H = 960, 700
ML, MR = 250, 30
BASELINE_SLUG = "gold_sdca_v6_reselect"


def fills_per_year(payload: dict) -> tuple[float, int, float]:
    """(sells/yr, fill sells, years) from a diagnostic tearsheet's dca block."""
    start = date.fromisoformat(payload["period_start"])
    end = date.fromisoformat(payload["period_end"])
    years = (end - start).days / 365.25
    sells = int(payload["dca"]["fill_sell_days"])
    return sells / years, sells, years


def load() -> dict:
    base = json.loads((PUBLIC_STRATEGIES / f"{BASELINE_SLUG}.json").read_text())
    base_yr, base_n, years = fills_per_year(base)
    votes = {}
    for vote, slug in (("v1", "gold_sdca_stagea_v1"), ("v2", "gold_sdca_stagea_v2")):
        diag = json.loads((PUBLIC_STRATEGIES / f"{slug}.json").read_text())
        gate = json.loads((ROOT / ".scratch" / f"gold_curve_search_stagea_{vote}.json").read_text())
        yr, n, _ = fills_per_year(diag)
        g = gate["gate"]
        votes[vote] = {
            "fills_yr": yr,
            "fills": n,
            "mult": yr / base_yr,
            "flat": float(g["mean_oos_vs_flat_dca_pct"]),
            "beats_flat": bool(g["beats_flat_dca_oos"]),
            "lump": float(g["mean_oos_vs_lump_dca_pct"]),
            "beats_lump": bool(g["beats_lump_oos"]),
            "sens": float(g["sensitivity_max_abs_delta"]),
            "frontier": int(g["frontier_beats_both"]),
            "frontier_total": int(g["frontier_total"]),
        }
    return {"base_yr": base_yr, "base_n": base_n, "years": years, "votes": votes}


def hbar(parts: list[str], y: float, h: float, frac: float, color: str, label: str) -> None:
    pw = W - ML - MR
    w = max(frac, 0.0) * pw
    parts.append(f'<rect x="{ML}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" fill="{color}"/>')
    parts.append(
        f'<text x="{ML + w + 8:.1f}" y="{y + h / 2 + 4:.1f}" font-size="12">{escape(label)}</text>'
    )


def svg_verdict(d: dict) -> str:
    v1, v2 = d["votes"]["v1"], d["votes"]["v2"]
    parts = [
        '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 960 700" font-family="sans-serif">',
        "<title>GLD Stage-A/B verdict: V1 vs V2 vs benchmarks</title>",
        f'<text x="{W / 2}" y="22" text-anchor="middle" font-size="15" '
        'font-weight="bold">GLD Stage-A/B verdict — V1 (valuation-only, barred) vs '
        "V2 (real_rate-only, candidate)</text>",
        f'<text x="{W / 2}" y="40" text-anchor="middle" font-size="11" fill="#333333">'
        "behavior window 2010-01-04→2026-09-29 (16.7yr) + Stage-B causal-rolling90 "
        "gate (3 folds, holdout absent)</text>",
        f'<text x="{W / 2}" y="56" text-anchor="middle" font-size="11" fill="#333333">'
        "V1-vs-V2 gap isolates the WEIGHT VECTOR under identical rolling90 rails — "
        "NOT trend evidence (frozen trend rails appear nowhere in the gate)</text>",
    ]
    # Panel A: behavior fills/yr (horizontal bars, scale 0..4).
    ay, ah, gap = 86, 26, 40
    parts.append(
        f'<text x="{W / 2}" y="{ay - 8}" text-anchor="middle" font-size="12" '
        'font-weight="bold">(A) behavior: sell fills/yr (reselect baseline '
        f"{d['base_yr']:.2f} = {d['base_n']} fills)</text>"
    )
    rows = [
        ("baseline reselect", d["base_yr"], "#666666", f"{d['base_yr']:.2f}/yr (1.00x)"),
        (
            "V1 valuation-only",
            v1["fills_yr"],
            "#c00000",
            f"{v1['fills_yr']:.2f}/yr ({v1['mult']:.2f}x) — FAILS oscillation",
        ),
        (
            "V2 real_rate-only",
            v2["fills_yr"],
            "#2a7a2a",
            f"{v2['fills_yr']:.2f}/yr ({v2['mult']:.2f}x) — oscillates",
        ),
    ]
    for i, (name, val, color, lab) in enumerate(rows):
        y = ay + i * (ah + gap - ah + 14)
        parts.append(
            f'<text x="{ML - 10}" y="{y + ah / 2 + 4:.1f}" text-anchor="end" font-size="12">{name}</text>'
        )
        hbar(parts, y, ah, val / 4.0, color, lab)
    # Panel B: gate means (grouped vertical bars, zero line, scale -6..+30).
    by0, by1 = 268, 470
    parts.append(
        f'<text x="{W / 2}" y="{by0 - 24}" text-anchor="middle" font-size="12" '
        'font-weight="bold">(B) gate: mean OOS vs flat (blue) and vs lump (orange), %</text>'
    )
    lo, hi = -6.0, 30.0

    def sy(v: float) -> float:
        return by1 - (v - lo) / (hi - lo) * (by1 - by0)

    for t in (-5, 0, 5, 10, 15, 20, 25, 30):
        y = sy(float(t))
        dash = ' stroke-dasharray="4,3"' if t == 0 else ""
        parts.append(
            f'<line x1="{ML}" y1="{y:.1f}" x2="{W - MR}" y2="{y:.1f}" '
            f'stroke="#{"000000" if t == 0 else "cccccc"}" stroke-width="1"{dash}/>'
        )
        parts.append(
            f'<text x="{ML - 6}" y="{y + 4:.1f}" text-anchor="end" font-size="11">{t}</text>'
        )
    for i, (name, v) in enumerate((("V1", v1), ("V2", v2))):
        cx = ML + (i + 0.5) * (W - ML - MR) / 2
        for j, (key, color, beat) in enumerate(
            ((("flat", "#1f5fa8", v["beats_flat"])), (("lump", "#b36b00", v["beats_lump"])))
        ):
            val = v[key]
            x = cx + (j - 0.5) * 56 - 25
            top, bot = (sy(val), sy(0.0)) if val >= 0 else (sy(0.0), sy(val))
            parts.append(
                f'<rect x="{x:.1f}" y="{top:.1f}" width="50" height="{max(bot - top, 1.5):.1f}" fill="{color}"/>'
            )
            tag = "beats" if beat else "MISS"
            parts.append(
                f'<text x="{x + 25:.1f}" y="{(top - 6):.1f}" text-anchor="middle" '
                f'font-size="11" font-weight="bold" fill="{"#2a7a2a" if beat else "#c00000"}">'
                f"{val:+.2f} ({tag})</text>"
            )
        verdict = (
            "benchmarks PASS, behavior FAILS"
            if name == "V1"
            else "lump MISS (-2.49), frontier 0/1728"
        )
        parts.append(
            f'<text x="{cx:.1f}" y="{by1 + 20}" text-anchor="middle" font-size="12" '
            f'font-weight="bold">{name}: sens {v["sens"]:.2f} stable, feasible 3/3 — {verdict}</text>'
        )
    parts.append(
        f'<rect x="{ML}" y="{by0}" width="{W - ML - MR}" height="{by1 - by0}" fill="none" stroke="#000000"/>'
    )
    # Panel C: frontier-both / 1728 (horizontal bars).
    cy = 528
    parts.append(
        f'<text x="{W / 2}" y="{cy - 8}" text-anchor="middle" font-size="12" '
        'font-weight="bold">(C) frontier: feasible shapes beating BOTH on mean OOS (/1728)</text>'
    )
    hbar(
        parts,
        cy + 6,
        ah,
        v1["frontier"] / v1["frontier_total"],
        "#1f5fa8",
        f"V1 {v1['frontier']}/{v1['frontier_total']}",
    )
    hbar(
        parts,
        cy + 6 + ah + 14,
        ah,
        0.5 / v2["frontier_total"],
        "#c00000",
        f"V2 {v2['frontier']}/{v2['frontier_total']} — no shape beats both",
    )
    # Footer: verdict.
    parts.append(
        f'<text x="{W / 2}" y="648" text-anchor="middle" font-size="12" font-weight="bold">'
        "VERDICT: NEITHER clears the combined bar — V1 benchmarks pass / behavior fails "
        "(unshippable); V2 behavior passes / lump fails (NEGATIVE)</text>"
    )
    parts.append(
        f'<text x="{W / 2}" y="668" text-anchor="middle" font-size="11" fill="#333333">'
        "oscillation-vs-lump tension now MEASURED (oscillating vote trails lump; "
        "lump-beating vote never trades), not theorized</text>"
    )
    parts.append(
        f'<text x="{W / 2}" y="686" text-anchor="middle" font-size="11" fill="#333333">'
        "Stage-A in-sample (selects nothing); V1 trend-rails selection lineage caveat "
        "recorded — owner's call whether it disqualifies (moot: fails oscillation)</text>"
    )
    parts.append("</svg>")
    return "\n".join(parts) + "\n"


def main() -> None:
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    PUBLIC_DIR.mkdir(parents=True, exist_ok=True)
    out = OUT_DIR / "gold_stagea_verdict.svg"
    out.write_text(svg_verdict(load()))
    shutil.copy(out, PUBLIC_DIR / "gold_stagea_verdict.svg")
    print(f"gold_stagea_verdict.svg: {out.stat().st_size} bytes (+ public/ copy)")


if __name__ == "__main__":
    main()
