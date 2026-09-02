#!/usr/bin/env python3
"""Cut the social advertising headers from the same identity as the OG card.

X (1500×500) and LinkedIn (1584×396 personal, 1128×191 company) are much shorter
than a 1200×630 Open Graph card. Cropping that card drops the domain into the
platform chrome. These headers keep the SAME copy — lowercase wordmark + block
cursor, the OG tagline, digithings.ai — in a COMPACT vertical stack that fits
inside each platform's crop, including X's avatar overlap and LinkedIn's side
crop.

Everything here is DERIVED:

  * copy is read from HEADLINES in build-og.py, so a header cannot invent a
    tagline;
  * the wordmark is OUTLINED with the same Geist Mono helper the OG cards use;
  * colours, cell width and cursor height are the OG constants.

Usage:
    frontend/digiweb/brand/build-header.py          # write headers + kit copies
    frontend/digiweb/brand/build-header.py --check   # verify, write nothing
"""

from __future__ import annotations

import argparse
import importlib.util
import shutil
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path

BRAND = Path(__file__).resolve().parent
REPO_ROOT = BRAND.parents[2]
OUT_DIR = BRAND / "headers"
EMAIL_DIR = BRAND / "email"
PUBLIC_BRAND = REPO_ROOT / "frontend" / "digithings-web" / "public" / "brand"
PUBLIC_OG_PNG = REPO_ROOT / "frontend" / "digithings-web" / "public" / "og.png"

# Vertical rhythm as a fraction of WORD_EM. OG used ~0.86 between word and
# tagline baselines and ~1.47 between tagline and domain (the domain sat as a
# footer). Headers collapse that footer gap so all three lines stay on-canvas.
LINE_RATIO = 30 / 116
DOMAIN_RATIO = 22 / 116
GAP_WORD_LINE = 0.42
GAP_LINE_DOMAIN = 0.40
DESCENDER = 0.28  # of domain_em, below the domain baseline
WORD_EM_CAP = 96.0  # never larger than a slightly-reduced OG wordmark

FORBIDDEN = (
    "12X",
    "Twelve X",
    "TwelveX",
    "Prime Terminal",
    "DigiThings",
    "DigiChat",
    "Digiquant",
)


@dataclass(frozen=True)
class FormatSpec:
    key: str
    width: int
    height: int
    frame: float
    safe_left: float
    safe_right: float
    safe_top: float
    safe_bottom: float
    filename: str

    @property
    def safe(self) -> tuple[float, float, float, float]:
        x = self.safe_left
        y = self.safe_top
        w = self.width - self.safe_left - self.safe_right
        h = self.height - self.safe_top - self.safe_bottom
        return x, y, w, h


# Safe insets are the crop, not the decorative frame:
#   X — side crop on mobile plus the profile photo overlapping the bottom-left.
#   LinkedIn personal — heavier side crop; the photo sits below the cover.
#   LinkedIn company — short banner; logo overlaps the bottom-left.
FORMATS: tuple[FormatSpec, ...] = (
    FormatSpec(
        key="x",
        width=1500,
        height=500,
        frame=24,
        safe_left=180,
        safe_right=180,
        safe_top=40,
        safe_bottom=88,
        filename="digithings-x-1500x500",
    ),
    FormatSpec(
        key="linkedin-personal",
        width=1584,
        height=396,
        frame=18,
        safe_left=240,
        safe_right=240,
        safe_top=28,
        safe_bottom=40,
        filename="digithings-linkedin-personal-1584x396",
    ),
    FormatSpec(
        key="linkedin-company",
        width=1128,
        height=191,
        frame=10,
        safe_left=72,
        safe_right=72,
        safe_top=14,
        safe_bottom=18,
        filename="digithings-linkedin-company-1128x191",
    ),
)


@dataclass(frozen=True)
class HeaderLayout:
    spec: FormatSpec
    word: str
    line: str
    domain: str
    cell_em: float
    cursor_h_em: float
    bg: str
    ink: str
    mute: str
    word_em: float
    line_em: float
    domain_em: float
    word_x: float
    word_baseline: float
    cursor_x: float
    cursor_y: float
    cursor_w: float
    cursor_h: float
    line_x: float
    line_baseline: float
    domain_x: float
    domain_baseline: float

    @property
    def stack_top(self) -> float:
        return self.cursor_y

    @property
    def stack_bottom(self) -> float:
        return self.domain_baseline + self.domain_em * DESCENDER

    def ink_box(self) -> tuple[float, float, float, float]:
        left = min(self.word_x, self.line_x, self.domain_x)
        right = max(
            self.cursor_x + self.cursor_w,
            self.line_x + len(self.line) * self.line_em * self.cell_em,
            self.domain_x + len(self.domain) * self.domain_em * self.cell_em,
        )
        return left, self.stack_top, right - left, self.stack_bottom - self.stack_top

    def inside_safe(self) -> bool:
        sx, sy, sw, sh = self.spec.safe
        x, y, w, h = self.ink_box()
        return x >= sx and y >= sy and x + w <= sx + sw and y + h <= sy + sh


def _load_og():
    path = BRAND / "build-og.py"
    spec = importlib.util.spec_from_file_location("digiweb_brand_build_og", path)
    if spec is None or spec.loader is None:
        raise SystemExit(f"cannot load {path}")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CURSOR_H_EM = 0.71  # matches build-og.py / TerminalMark; asserted against the OG module


def word_em_for(spec: FormatSpec, word: str, line: str, domain: str, cell_em: float) -> float:
    _sx, _sy, sw, sh = spec.safe
    stack_ratio = CURSOR_H_EM + GAP_WORD_LINE + GAP_LINE_DOMAIN + DOMAIN_RATIO * DESCENDER
    max_h = sh / stack_ratio
    max_word = sw / ((len(word) + 1) * cell_em)
    max_line = sw / (len(line) * LINE_RATIO * cell_em)
    max_domain = sw / (len(domain) * DOMAIN_RATIO * cell_em)
    return min(WORD_EM_CAP, max_h, max_word, max_line, max_domain)


def layout(og, spec: FormatSpec) -> HeaderLayout:
    copy = og.HEADLINES["digithings"]
    word, line, domain = copy["word"], copy["line"], copy["domain"]
    cell, cursor_h = og.CELL_EM, og.CURSOR_H_EM
    if cursor_h != CURSOR_H_EM:
        raise SystemExit(f"CURSOR_H_EM drifted from build-og.py ({cursor_h})")
    word_em = word_em_for(spec, word, line, domain, cell)
    line_em = word_em * LINE_RATIO
    domain_em = word_em * DOMAIN_RATIO
    cursor_w = word_em * cell
    cursor_h_px = word_em * cursor_h

    stack_top_span = cursor_h_px
    stack_h = (
        cursor_h_px + word_em * GAP_WORD_LINE + word_em * GAP_LINE_DOMAIN + domain_em * DESCENDER
    )
    _sx, sy, _sw, sh = spec.safe
    stack_top = sy + (sh - stack_h) / 2
    word_baseline = stack_top + stack_top_span
    line_baseline = word_baseline + word_em * GAP_WORD_LINE
    domain_baseline = line_baseline + word_em * GAP_LINE_DOMAIN

    lockup_w = (len(word) + 1) * word_em * cell
    line_w = len(line) * line_em * cell
    domain_w = len(domain) * domain_em * cell
    # Centre on the canvas, then the safe-rect assertion catches a crop miss.
    word_x = (spec.width - lockup_w) / 2
    return HeaderLayout(
        spec=spec,
        word=word,
        line=line,
        domain=domain,
        cell_em=cell,
        cursor_h_em=cursor_h,
        bg=og.BG,
        ink=og.INK,
        mute=og.MUTE,
        word_em=word_em,
        line_em=line_em,
        domain_em=domain_em,
        word_x=word_x,
        word_baseline=word_baseline,
        cursor_x=word_x + len(word) * word_em * cell,
        cursor_y=word_baseline - cursor_h_px,
        cursor_w=cursor_w,
        cursor_h=cursor_h_px,
        line_x=(spec.width - line_w) / 2,
        line_baseline=line_baseline,
        domain_x=(spec.width - domain_w) / 2,
        domain_baseline=domain_baseline,
    )


def header_svg(og, lay: HeaderLayout) -> str:
    spec = lay.spec
    w, h, frame = spec.width, spec.height, spec.frame
    outline = og.outline
    font = og._font()
    return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{w}" height="{h}" viewBox="0 0 {w} {h}">
  <!-- GENERATED by frontend/digiweb/brand/build-header.py — do not hand-edit.
       Compact social header: same copy as the OG card (HEADLINES in build-og.py),
       outlined Geist Mono, tightened vertical stack so the domain survives the
       {spec.key} crop. Not a scaled 1200×630 card. -->
  <rect width="{w}" height="{h}" fill="{lay.bg}"/>
  <rect x="{frame + 0.5}" y="{frame + 0.5}" width="{w - 2 * frame - 1}" height="{h - 2 * frame - 1}"
        fill="none" stroke="{lay.mute}" stroke-opacity="0.28" stroke-width="1"/>
  <g>
    {outline(font, lay.word, lay.word_em, lay.word_x, lay.word_baseline, lay.ink)}
  </g>
  <rect x="{lay.cursor_x:.2f}" y="{lay.cursor_y:.2f}"
        width="{lay.cursor_w:.2f}" height="{lay.cursor_h:.2f}" fill="{lay.ink}"/>
  <g>
    {outline(font, lay.line, lay.line_em, lay.line_x, lay.line_baseline, lay.mute)}
  </g>
  <g>
    {outline(font, lay.domain, lay.domain_em, lay.domain_x, lay.domain_baseline, lay.mute)}
  </g>
</svg>
"""


def signoff_text(copy: dict[str, str]) -> str:
    return f"{copy['word']}\n{copy['line']}\nhttps://{copy['domain']}\n"


def signoff_html(copy: dict[str, str]) -> str:
    # Inline hex: email clients do not read design tokens. Light ink on a
    # transparent/white thread — the usual company-mail background.
    word, line, domain = copy["word"], copy["line"], copy["domain"]
    return (
        '<table role="presentation" cellpadding="0" cellspacing="0" '
        "style=\"font-family:ui-monospace,'Geist Mono',Menlo,Consolas,monospace;"
        'font-size:14px;line-height:1.5;color:#14181B;">\n'
        "  <tr><td>\n"
        f"    {word}<br>\n"
        f"    {line}<br>\n"
        f'    <a href="https://{domain}" style="color:#14181B;text-decoration:none;">'
        f"{domain}</a>\n"
        "  </td></tr>\n"
        "</table>\n"
    )


def kit_copies() -> list[tuple[Path, Path]]:
    """Canonical kit file → served copy under digithings-web/public."""
    pairs: list[tuple[Path, Path]] = []
    for spec in FORMATS:
        for ext in (".svg", ".png"):
            src = OUT_DIR / f"{spec.filename}{ext}"
            pairs.append((src, PUBLIC_BRAND / "headers" / f"{spec.filename}{ext}"))
    for name in ("dark", "light"):
        for suffix in (".svg", ".png", "-500.png"):
            src = BRAND / "avatar" / f"digithings-avatar-{name}{suffix}"
            pairs.append((src, PUBLIC_BRAND / "avatar" / src.name))
    pairs.append((BRAND / "og" / "digithings-og.svg", PUBLIC_BRAND / "og" / "digithings-og.svg"))
    pairs.append((BRAND / "og" / "digithings-og.png", PUBLIC_BRAND / "og" / "digithings-og.png"))
    pairs.append((BRAND / "og" / "digithings-og.png", PUBLIC_OG_PNG))
    pairs.append((EMAIL_DIR / "signoff.txt", PUBLIC_BRAND / "email" / "signoff.txt"))
    pairs.append((EMAIL_DIR / "signoff.html", PUBLIC_BRAND / "email" / "signoff.html"))
    return pairs


def _reject_forbidden(text: str, where: str) -> None:
    for needle in FORBIDDEN:
        if needle in text:
            raise SystemExit(f"{where} contains forbidden copy {needle!r}")


def _same(path: Path, body: str | bytes) -> bool:
    if not path.exists():
        return False
    if isinstance(body, bytes):
        return path.read_bytes() == body
    return path.read_text(encoding="utf-8") == body


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()

    og = _load_og()
    copy = og.HEADLINES["digithings"]
    layouts = {spec.key: layout(og, spec) for spec in FORMATS}
    for lay in layouts.values():
        if not lay.inside_safe():
            raise SystemExit(f"{lay.spec.key}: ink {lay.ink_box()} escapes safe {lay.spec.safe}")
        if lay.stack_bottom - lay.stack_top >= lay.spec.height * (
            0.90 if lay.spec.key == "linkedin-company" else 0.55
        ):
            raise SystemExit(f"{lay.spec.key}: stack is not compact enough")
        if lay.spec.key != "linkedin-company" and lay.domain_baseline >= lay.spec.height * 0.72:
            raise SystemExit(
                f"{lay.spec.key}: domain sits too low — it will crop like a tall OG card"
            )

    svgs = {spec.key: header_svg(og, layouts[spec.key]) for spec in FORMATS}
    txt = signoff_text(copy)
    html = signoff_html(copy)
    _reject_forbidden(txt, "signoff.txt")
    _reject_forbidden(html, "signoff.html")
    for key, svg in svgs.items():
        _reject_forbidden(svg, f"{key} svg")
        if "<text" in svg:
            raise SystemExit(f"{key} used <text> — outline the wordmark")

    if args.check:
        stale = False
        for spec in FORMATS:
            target = OUT_DIR / f"{spec.filename}.svg"
            if not _same(target, svgs[spec.key]):
                print(f"❌  {target.name} is stale — re-run build-header.py", file=sys.stderr)
                stale = True
        if not _same(EMAIL_DIR / "signoff.txt", txt):
            print("❌  email/signoff.txt is stale — re-run build-header.py", file=sys.stderr)
            stale = True
        if not _same(EMAIL_DIR / "signoff.html", html):
            print("❌  email/signoff.html is stale — re-run build-header.py", file=sys.stderr)
            stale = True
        for src, dest in kit_copies():
            if not src.exists() or not dest.exists() or src.read_bytes() != dest.read_bytes():
                print(
                    f"❌  {dest.relative_to(REPO_ROOT)} is stale — re-run build-header.py",
                    file=sys.stderr,
                )
                stale = True
        if stale:
            return 1
        print("social headers: in sync ✅")
        return 0

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    EMAIL_DIR.mkdir(parents=True, exist_ok=True)
    for spec in FORMATS:
        (OUT_DIR / f"{spec.filename}.svg").write_text(svgs[spec.key], encoding="utf-8")
    (EMAIL_DIR / "signoff.txt").write_text(txt, encoding="utf-8")
    (EMAIL_DIR / "signoff.html").write_text(html, encoding="utf-8")

    script = """
const sharp = require("sharp"), fs = require("fs"), dir = process.argv[1];
const names = %s;
(async () => {
  for (const n of names) {
    const svg = fs.readFileSync(`${dir}/${n}.svg`);
    const f = `${dir}/${n}.png`;
    await sharp(svg).png({ compressionLevel: 9 }).toFile(f);
    const m = await sharp(f).metadata();
    console.log(`  ${n}.png  ${m.width}x${m.height}  ${(fs.statSync(f).size / 1024).toFixed(1)}KB`);
  }
})().catch((e) => { console.error(e.message); process.exit(1); });
""" % [spec.filename for spec in FORMATS]
    subprocess.run(["node", "-e", script, str(OUT_DIR)], cwd=REPO_ROOT, check=True)

    for src, dest in kit_copies():
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dest)

    print("\nsocial headers: rebuilt ✅")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
