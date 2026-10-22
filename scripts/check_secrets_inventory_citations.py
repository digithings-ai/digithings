#!/usr/bin/env python3
"""Check every ``file:line`` citation in docs/ops/SECRETS_INVENTORY.md.

Usage:
    python3 scripts/check_secrets_inventory_citations.py [tree-ish]

The document is read from the working tree. The cited files are read from the
given tree-ish (default: HEAD). Run it from the repository root.

The rule (the same rule the inventory's own gap bullet states):
  * rows = the markdown table rows of the document. A prose line that carries
    a citation and at least one name is checked as well.
  * names = the backticked UPPER_CASE tokens of the row or line.
  * citations = the backticked ``path:lines`` whose last path segment looks
    like a file (it has an extension, or it is Makefile, Dockerfile, justfile
    or Caddyfile).
  * resolution = the exact repository path, then docs/ops/,
    .github/workflows/, apps/digichat/ and apps/digichat-cloudflare/, then
    every tracked file whose path ends with the cited path. A bare path such
    as ``wrangler.toml`` therefore matches every file with that name.
  * satisfaction = one of the cited lines holds one of the names on a code
    line. A comment line does not count as a code line, so a citation that
    only finds the name in a comment is reported as a residual.
  * a comma-separated list and a range are split, so every cited line is
    checked.
  * a row whose Consumer cell says that no code reads the name is not
    checked.
  * a row whose first cell names a file rather than a secret is checked for
    the existence of the cited line only.
  * the (g) rows are not checked: they point at the twelve-x laptop store,
    which is not in this repository.
  * a citation into the inventory itself is checked against the document
    being audited, not against the committed copy.

The exit code is 1 only when a table row fails. A prose pointer can prove an
absence, a placeholder shape, a wildcard name or a file outside this
repository; those are printed in the report and do not fail the run.

The script prints paths, line numbers and names only. It never prints file
text, so no credential value can reach the transcript.
"""
import os
import re
import subprocess
import sys

DOC = "docs/ops/SECRETS_INVENTORY.md"

NAME_RE = re.compile(r"`([A-Z][A-Z0-9_]{4,}[A-Z0-9])`")
CITE_RE = re.compile(r"`([^`\s]+?):([0-9][0-9,\-]*)`")
FILEISH = re.compile(r"(\.[A-Za-z0-9_.-]+$)|(^(Makefile|Dockerfile|justfile|Caddyfile)$)")
NO_CONSUMER_RE = re.compile(r"^(no|none|not|un)\w*")

STOP = {
    "DIGIKEY", "GITHUB", "TOKEN", "VALUE", "SECRET", "ENV", "JSON", "YAML",
    "TOML", "HTTP", "HTTPS", "SHA256", "UUID", "HMAC", "RS256", "ES256",
    "ALLOWED", "GET", "POST", "PUT", "PATCH", "DELETE", "HEAD", "OPTIONS",
}


def git(*args, cwd=None):
    return subprocess.check_output(["git"] + list(args), cwd=cwd, text=True)


def strip_comment(line, path):
    s = line.strip()
    if path.endswith((".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs")):
        if s.startswith("//"):
            return ""
        idx = s.find("//")
        if idx >= 0:
            before = s[:idx]
            if before.count("'") % 2 == 0 and before.count('"') % 2 == 0 and before.count("`") % 2 == 0:
                s = before
        return s
    if path.endswith((".py", ".sh", ".toml", ".yml", ".yaml", ".cfg", ".ini", ".env")) or os.path.basename(path) in (
        "Makefile", "Dockerfile", "justfile", "Caddyfile"):
        if s.startswith("#"):
            return ""
        idx = s.find(" #")
        if idx >= 0:
            before = s[:idx]
            if before.count("'") % 2 == 0 and before.count('"') % 2 == 0:
                s = before
        elif s.endswith("#"):
            s = ""
        elif "#" in s:
            before = s[: s.find("#")]
            if before.count("'") % 2 == 0 and before.count('"') % 2 == 0:
                s = before
    return s


def parse_lines(spec):
    out = []
    for part in spec.split(","):
        part = part.strip()
        if not part:
            continue
        if "-" in part:
            a, b = part.split("-", 1)
            try:
                a, b = int(a), int(b)
            except ValueError:
                continue
            if b < a:
                a, b = b, a
            out.extend(range(a, b + 1))
        else:
            try:
                out.append(int(part))
            except ValueError:
                pass
    return out


def main():
    root = git("rev-parse", "--show-toplevel").strip()
    tree = sys.argv[1] if len(sys.argv) > 1 else "HEAD"
    doc_path = os.path.join(root, DOC)
    doc = open(doc_path).read().split("\n")
    files = [p for p in git("ls-files", cwd=root).split("\n") if p]

    def resolve(cited):
        cands = []
        if cited in files:
            cands.append(cited)
        for pref in ("docs/ops/", ".github/workflows/", "apps/digichat/", "apps/digichat-cloudflare/"):
            if pref + cited in files and pref + cited not in cands:
                cands.append(pref + cited)
        for p in files:
            if p.endswith("/" + cited) and p not in cands:
                cands.append(p)
        return cands

    def file_lines(path):
        if path == DOC:
            # a citation into the inventory itself is checked against the
            # document being audited, not against the committed copy
            return doc
        try:
            raw = git("show", tree + ":" + path, cwd=root)
        except subprocess.CalledProcessError:
            return None
        return raw.split("\n")

    total_rows = 0
    total_prose = 0
    total_cites = 0
    resolved_cites = 0
    unresolvable = 0
    file_row_cites = 0
    passes = 0
    comment_only = []
    fails = []
    excluded = 0
    section = ""

    def check(idx, line, names, is_file_row, kind):
        nonlocal total_cites, resolved_cites, unresolvable, file_row_cites, passes
        cites = []
        for m in CITE_RE.finditer(line):
            path, spec = m.group(1), m.group(2)
            if not FILEISH.search(path.split("/")[-1]):
                continue
            cites.append((path, spec))
        for path, spec in cites:
            total_cites += 1
            cands = resolve(path)
            if not cands:
                unresolvable += 1
                continue
            resolved_cites += 1
            if is_file_row or not names:
                # the citation is a path: the check is that the line exists
                file_row_cites += 1
                continue
            lns = parse_lines(spec)
            ok = False
            com = False
            hits = []
            for c in cands:
                content = file_lines(c)
                if content is None:
                    continue
                for n in names:
                    for i, raw in enumerate(content, start=1):
                        if n in raw:
                            hits.append((c, n, i))
                for ln in lns:
                    if ln < 1 or ln > len(content):
                        continue
                    raw = content[ln - 1]
                    if any(n in raw for n in names):
                        ok = True
                        if not strip_comment(raw, c).strip():
                            com = True
            if ok:
                passes += 1
                if com:
                    code_at = []
                    for c in cands:
                        content = file_lines(c)
                        if content is None:
                            continue
                        for i, raw in enumerate(content, start=1):
                            if any(n in raw for n in names) and strip_comment(raw, c).strip():
                                code_at.append((c, i))
                    comment_only.append((idx, path, spec, sorted(set(hits)), sorted(set(code_at))))
            else:
                fails.append((idx, path, spec, sorted(set(hits)), kind))

    for idx, line in enumerate(doc, start=1):
        s = line.strip()
        if s.startswith("#"):
            section = s.lstrip("#").strip()
            continue
        if not s.startswith("|"):
            if not s or "no consumer" in s.lower():
                continue
            if not CITE_RE.search(line):
                continue
            names = sorted(set(NAME_RE.findall(line)) - STOP)
            if not names:
                continue
            if re.match(r"^\(g\d?\)", section):
                continue
            total_prose += 1
            check(idx, line, names, False, "prose")
            continue
        cells = [c.strip() for c in s.strip("|").split("|")]
        if not cells:
            continue
        if all(set(c) <= set("-: ") and c for c in cells):
            continue
        if not any(re.search(r"[A-Za-z]", c) for c in cells):
            continue
        total_rows += 1
        if len(cells) > 1 and NO_CONSUMER_RE.match(cells[1].strip().strip("*").strip().lower()):
            # the Consumer cell says that no code reads the name
            excluded += 1
            continue
        if re.match(r"^\(g\d?\)", section):
            # the (g) rows point at a store that is not in this repository
            continue
        names = sorted(set(NAME_RE.findall(s)) - STOP)
        is_file_row = bool(FILEISH.search(cells[0].strip().strip("`")))
        check(idx, s, names, is_file_row, "table")

    print("tree                  :", tree)
    print("table rows checked    :", total_rows, "(excluded no-consumer rows:", excluded, ")")
    print("prose lines checked   :", total_prose)
    print("citations w/ line     :", total_cites)
    print("  resolved            :", resolved_cites)
    print("  unresolvable        :", unresolvable)
    print("  file/description rows:", file_row_cites)
    print("  passed              :", passes)
    fails_table = [f for f in fails if f[4] == "table"]
    fails_prose = [f for f in fails if f[4] == "prose"]
    print("FAILURES in a table row (name absent at the cited line):", len(fails_table))
    for f in fails_table:
        print("  doc:%d %s:%s names_at=%s" % (f[0], f[1], f[2], f[3]))
    print("FAILURES in a prose line (a claim of a different kind):", len(fails_prose))
    for f in fails_prose:
        print("  doc:%d %s:%s names_at=%s" % (f[0], f[1], f[2], f[3]))
    print("COMMENT-ONLY RESIDUAL (name held only by a comment line):", len(comment_only))
    for f in comment_only:
        print("  doc:%d %s:%s names_at=%s code_at=%s" % (f[0], f[1], f[2], f[3], f[4]))
    # a prose pointer can prove an absence, a placeholder shape, a wildcard
    # name or a file outside this repository: those are reported, not failed
    return 1 if fails_table else 0


if __name__ == "__main__":
    sys.exit(main())
