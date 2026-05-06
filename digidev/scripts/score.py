#!/usr/bin/env python3
"""
digidev quality gate scorer.

Reads staged diff, runs heuristic checks, and validates self-reported
dimension scores against thresholds in agents.yml.

Usage:
  python3 scripts/score.py                               # heuristics + show rubrics
  python3 scripts/score.py --set security=8,quality=9,optimization=7,accuracy=9
  python3 scripts/score.py --delta                       # diff vs base branch
"""
import json
import re
import subprocess
import sys
from pathlib import Path

DIMENSIONS = ["security", "quality", "optimization", "accuracy"]
DEFAULTS = {"security": 8, "quality": 8, "optimization": 7, "accuracy": 9}

# ── Heuristic patterns ────────────────────────────────────────────────────────

_SEC = [
    (r'(?i)(?:api_key|apikey|secret_key|password|passwd|token)\s*=\s*["\'][^"\'$\{]{6,}["\']',
     "Possible hardcoded credential"),
    (r'subprocess\.[^\n]+shell\s*=\s*True',
     "subprocess(shell=True) — command injection risk"),
    (r'\beval\s*\([^\n)]+\)',
     "eval() call — code injection risk"),
    (r'(?m)^[+][^+].*\b0\.0\.0\.0\b',
     "Binding to 0.0.0.0 — broad network exposure"),
    (r'(?im)^[+][^+].*#\s*TODO.*(auth|security|permission|password|secret)',
     "Security TODO left unresolved in staged changes"),
]

_QUAL = [
    (r'(?m)^[+][^+].*#\s*TODO\b', "TODO added in staged changes"),
    (r'(?m)^[+][^+].{121,}',      "Line >120 chars added"),
]

_OPT = [
    (r'(?s)for\s+\w+\s+in\s+.{1,80}:\n(?:\s+.+\n){0,3}\s+(?:await\s+)?(?:\w+\.)+(?:query|execute|find|get|fetch|select|insert|update)\(',
     "Query inside loop — possible N+1"),
    (r'await\s+\w[\w.()]+\s*\n\s*await\s+\w',
     "Sequential awaits — consider gather/Promise.all"),
]

# ── Helpers ───────────────────────────────────────────────────────────────────

def _run(*cmd):
    return subprocess.run(list(cmd), capture_output=True, text=True)


def get_thresholds():
    path = Path("agents.yml")
    if not path.exists():
        return dict(DEFAULTS)
    try:
        import yaml
        cfg = yaml.safe_load(path.read_text()) or {}
        t = cfg.get("scoring_thresholds", {})
        return {d: int(t.get(d, DEFAULTS[d])) for d in DIMENSIONS}
    except ImportError:
        pass
    txt = path.read_text()
    result = dict(DEFAULTS)
    for dim in DIMENSIONS:
        m = re.search(rf"^\s+{dim}:\s*(\d+)", txt, re.MULTILINE)
        if m:
            result[dim] = int(m.group(1))
    return result


def staged_files():
    return [f for f in _run("git", "diff", "--cached", "--name-only").stdout.strip().splitlines() if f]


def staged_diff():
    return _run("git", "diff", "--cached").stdout


def run_lint(files):
    py = [f for f in files if f.endswith(".py") and Path(f).exists()]
    js = [f for f in files if f.endswith((".js", ".ts", ".tsx", ".jsx")) and Path(f).exists()]
    errors = []
    if py and _run("which", "ruff").returncode == 0:
        r = _run("ruff", "check", *py)
        if r.returncode != 0:
            errors.append(("ruff", r.stdout.strip()[:400]))
    if js and _run("which", "eslint").returncode == 0:
        r = _run("npx", "--no-install", "eslint", *js)
        if r.returncode != 0:
            errors.append(("eslint", r.stdout.strip()[:400]))
    return errors


def heuristic(diff, patterns):
    return [msg for pat, msg in patterns if re.search(pat, diff)]


def test_coverage(files):
    src = [f for f in files if not re.search(r'test|spec', f, re.I)]
    tests = [f for f in files if re.search(r'test|spec', f, re.I)]
    if src and not tests:
        return ["Source files staged without test files — verify coverage exists"]
    return []


def read_criteria(dim):
    path = Path(f"docs/scoring/{dim.upper()}.md")
    if not path.exists():
        return [f"(rubric missing — re-run installer to generate docs/scoring/{dim.upper()}.md)"]
    text = path.read_text()
    criteria = re.findall(r'^\d+\.\s+\*\*(.+?)\*\*', text, re.MULTILINE)
    if not criteria:
        criteria = re.findall(r'^\d+\.\s+(.+)', text, re.MULTILINE)
    return criteria[:10]


# ── Colours ───────────────────────────────────────────────────────────────────

_tty = sys.stdout.isatty()
G = "\033[32m" if _tty else ""
R = "\033[31m" if _tty else ""
Y = "\033[33m" if _tty else ""
B = "\033[1m"  if _tty else ""
X = "\033[0m"  if _tty else ""

def _ok(m):   print(f"  {G}✓{X} {m}")
def _warn(m): print(f"  {Y}⚠{X}  {m}")
def _err(m):  print(f"  {R}✗{X} {m}")
def _sec(t):  print(f"\n{B}── {t} {'─' * max(0, 52 - len(t))}{X}\n")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    args = sys.argv[1:]
    set_raw  = next((a.split("=", 1)[1] for a in args if a.startswith("--set=")), None)
    do_delta = "--delta" in args

    thresholds = get_thresholds()
    files = staged_files()

    print(f"\n{B}╔{'═'*54}╗{X}")
    print(f"{B}║{'digidev — Quality Gate Score':^54}║{X}")
    print(f"{B}╚{'═'*54}╝{X}")

    if not files:
        print("\nNo staged changes. Run 'git add <files>' first.\n")
        sys.exit(0)

    _sec("Staged files")
    for f in files:
        print(f"  {f}")
    if do_delta:
        branch = _run("git", "rev-parse", "--abbrev-ref", "HEAD").stdout.strip()
        print(f"\n  (comparing HEAD vs origin/{branch})")

    diff = staged_diff()

    # ── Lint check ──
    _sec("Automated checks")
    lint_errors = run_lint(files)
    if lint_errors:
        for tool, output in lint_errors:
            _err(f"Lint ({tool}) failed")
            print(f"    {output}")
        print(f"\n  {R}Fix lint errors before scoring.{X}\n")
        sys.exit(1)
    _ok("Lint clean")

    warnings = {
        "Security":     heuristic(diff, _SEC),
        "Quality":      heuristic(diff, _QUAL),
        "Optimization": heuristic(diff, _OPT),
        "Accuracy":     test_coverage(files),
    }
    any_warn = False
    for dim, findings in warnings.items():
        for f in findings:
            any_warn = True
            _warn(f"{dim}: {f}")
    if not any_warn:
        _ok("No heuristic issues found")

    # ── Self-score validation ──
    if set_raw:
        _sec("Submitted scores")
        submitted = {}
        for part in set_raw.split(","):
            if "=" in part:
                k, v = part.strip().split("=", 1)
                submitted[k.strip().lower()] = int(v.strip())

        all_pass = True
        results = {}
        for dim in DIMENSIONS:
            score = submitted.get(dim)
            thr   = thresholds[dim]
            if score is None:
                _err(f"{dim.upper()}: not provided (required)")
                all_pass = False
                continue
            passed = score >= thr
            results[dim] = {"score": score, "threshold": thr, "passed": passed}
            if passed:
                _ok(f"{dim.upper()}: {score}/10  (≥{thr} required)")
            else:
                _err(f"{dim.upper()}: {score}/10  (≥{thr} required — FAIL)")
                all_pass = False

        print()
        if all_pass:
            print(f"  {G}{B}PASS{X} — all dimensions meet thresholds.\n")
            Path(".score-last.json").write_text(json.dumps(results, indent=2))
            sys.exit(0)
        else:
            failing = [d for d in DIMENSIONS if d in results and not results[d]["passed"]]
            print(f"  {R}{B}FAIL{X} — {', '.join(failing)} below threshold.\n")
            print(f"  Read docs/scoring/<DIMENSION>.md or run the score-and-fix skill.\n")
            sys.exit(1)

    # ── Show rubrics for self-review ──
    _sec("Rubrics — score yourself against each dimension")
    for dim in DIMENSIONS:
        print(f"  {B}{dim.upper()}{X}  (threshold: ≥{thresholds[dim]}/10)")
        for i, c in enumerate(read_criteria(dim), 1):
            print(f"    {i:2}. {c}")
        print()

    _sec("Submit your self-score")
    print(f"  {B}make score SCORES=\"security=?,quality=?,optimization=?,accuracy=?\"{X}")
    print(f"  Replace ? with your honest score (0–10) for each dimension.\n")
    sys.exit(0)


if __name__ == "__main__":
    main()
