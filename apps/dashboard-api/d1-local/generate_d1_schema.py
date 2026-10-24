#!/usr/bin/env python3
"""Regenerate the D1 (SQLite) schema for the core digithings schema (DIG-2891).

Reads the PostgreSQL schema of record -- digiquant/supabase/migrations/*.sql at
a git ref -- and emits ordered, idempotent SQLite migration files into this
directory's migrations/ folder, for local D1 (`wrangler dev --local`).

Deliberately NOT done here:
  * no data, no seed, no row import (gated on DIG-2888, the snapshot);
  * no Supabase connection, read or write;
  * no Cloudflare production binding, deploy or cutover;
  * no triggers or views -- SQLite has no TRUNCATE trigger, and the views use
    PostgreSQL-only SQL (:: casts, OVER, generate_series, DISTINCT ON).

The PG schema is the source of truth. If this output and a PG migration
disagree, the PG migration wins and this output is regenerated.

Usage:
    python3 apps/dashboard-api/d1-local/generate_d1_schema.py [--ref <git-ref>]
                                                                [--out <dir>]
                                                                [--repo <path>]

Defaults: --ref github/develop, --out <this dir>/migrations, --repo cwd.
"""
import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

REPO_MIGRATIONS = "digiquant/supabase/migrations"
CUTOVER = "cutover/"

ARGS = ap = argparse.ArgumentParser(description=__doc__)
ARGS.add_argument("--ref", default="github/develop",
                  help="git ref holding the PG schema of record")
ARGS.add_argument("--out", default=os.path.join(os.path.dirname(os.path.abspath(__file__)), "migrations"),
                  help="directory to write SQLite migration files into")
ARGS.add_argument("--repo", default=os.getcwd(),
                  help="path inside the digithings repo (default: cwd)")
ARGS.add_argument("--keep-corpus", action="store_true",
                  help="keep the materialised PG corpus for inspection")
ARGS = ap.parse_args()

REF, OUT, REPO = ARGS.ref, ARGS.out, ARGS.repo
WORK = tempfile.mkdtemp(prefix="dig2891-d1schema-")


def repo_root():
    """Walk up from --repo to the repository root.

    Deliberately NOT from __file__: this script is sometimes run from a scratch
    directory, and walking up from there reaches "/" where git fails with
    "not a git repository".
    """
    d = os.path.abspath(REPO)
    while not os.path.isdir(os.path.join(d, ".git")) and os.path.dirname(d) != d:
        d = os.path.dirname(d)
    if not os.path.isdir(os.path.join(d, ".git")):
        raise SystemExit("no git repository at or above %s (pass --repo)" % REPO)
    return d


def git(*args):
    return subprocess.run(("git",) + args, cwd=repo_root(), check=True,
                          capture_output=True, text=True)


def fetch_corpus():
    """Materialise every non-cutover PG migration at REF into one corpus file.

    `git cat-file -p ref:path` is the form that works on this blobless clone;
    `git show <ref> <path>` returns 0 bytes with rc=0 here.
    """
    listing = git("ls-tree", "-r", REF, "--name-only", "--", REPO_MIGRATIONS).stdout
    files = sorted(f for f in listing.splitlines()
                   if f.endswith(".sql") and CUTOVER not in f)
    if not files:
        raise SystemExit("no migrations found at %s -- wrong --ref?" % REF)
    offset, manifest, failed = 0, [], []
    with open(os.path.join(WORK, "all.sql"), "w", encoding="utf-8") as out:
        for f in files:
            p = subprocess.run(("git", "cat-file", "-p", "%s:%s" % (REF, f)),
                               cwd=repo_root(), capture_output=True)
            if p.returncode != 0:
                failed.append(f)
                continue
            text = p.stdout.decode("utf-8")
            out.write(text)
            manifest.append("%d\t%s" % (offset, f))
            offset += len(text.encode("utf-8"))
    if failed:
        raise SystemExit("git cat-file failed for %d file(s): %s" % (len(failed), failed[:3]))
    with open(os.path.join(WORK, "manifest.tsv"), "w") as fh:
        fh.write("\n".join(manifest) + "\n")
    print("ref                =", REF)
    print("migrations         =", len(files))
    print("corpus_bytes       =", offset)
    assert offset > 0, "empty corpus -- the fetch did not work"
    return len(files)


fetch_corpus()

import json, os, re, sys

CORPUS = os.path.join(WORK, "all.sql")
MANIFEST = os.path.join(WORK, "manifest.tsv")

# ---- mask comments / strings / dollar-quoted bodies -----------------------
def mask(src):
    """PROVEN real-code mask (verbatim from census3.py, which has a firing control).
    1 = real DDL char, 0 = inside comment / string / dollar-quoted body."""
    n = len(src)
    real = bytearray([1]) * n
    i = 0
    while i < n:
        c = src[i]
        if c == '-' and i+1 < n and src[i+1] == '-':
            j = src.find('\n', i); j = n if j < 0 else j
            for k in range(i, j): real[k] = 0
            i = j
        elif c == '/' and i+1 < n and src[i+1] == '*':
            j = src.find('*/', i+2); j = n if j < 0 else j+2
            for k in range(i, j): real[k] = 0
            i = j
        elif c in ("'", '"'):
            q = c; j = i+1
            while j < n:
                if src[j] == '\\': j += 2; continue
                if src[j] == q:
                    if j+1 < n and src[j+1] == q: j += 2; continue
                    j += 1; break
                j += 1
            for k in range(i+1, min(j-1, n)): real[k] = 0
            i = j
        elif c == '$':
            m = re.match(r'\$[A-Za-z_0-9]*\$', src[i:])
            if m:
                tag = m.group(0); j = src.find(tag, i+len(tag))
                j = n if j < 0 else j + len(tag)
                for k in range(i, j): real[k] = 0
                i = j
            else: i += 1
        else: i += 1
    assert len(real) == n
    return real

def blank_comments(src):
    """Length-preserving copy with -- and /* */ comment text replaced by spaces.
    String literals are LEFT intact so DEFAULT 'x' stays readable. Needed because
    splitting a table body on the raw source lets a comma inside a comment invent
    a phantom column (measured: 24 phantom types)."""
    out = list(src)
    n = len(src); i = 0
    while i < n:
        c = src[i]
        if c == '-' and i+1 < n and src[i+1] == '-':
            j = src.find('\n', i); j = n if j < 0 else j
            for k in range(i, j): out[k] = ' '
            i = j
        elif c == '/' and i+1 < n and src[i+1] == '*':
            j = src.find('*/', i+2); j = n if j < 0 else j+2
            for k in range(i, j):
                if out[k] != '\n': out[k] = ' '
            i = j
        else: i += 1
    return ''.join(out)

def body(src, start):
    """Balanced-paren body beginning at the '(' at/after start."""
    i = src.index("(", start); depth = 0
    for j in range(i, len(src)):
        if src[j] == "(": depth += 1
        elif src[j] == ")":
            depth -= 1
            if depth == 0: return src[i + 1:j], j
    raise ValueError("unbalanced")

def split_top(s, sep=","):
    out, depth, cur, q = [], 0, [], None
    for ch in s:
        if q:
            cur.append(ch)
            if ch == q: q = None
            continue
        if ch in "'\"":
            q = ch; cur.append(ch); continue
        if ch == "(": depth += 1
        elif ch == ")": depth -= 1
        if ch == sep and depth == 0: out.append("".join(cur)); cur = []
        else: cur.append(ch)
    if "".join(cur).strip(): out.append("".join(cur))
    return out

# ---- PG type -> SQLite ---------------------------------------------------
TYPE_MAP = {
    "uuid": "TEXT", "text": "TEXT", "varchar": "TEXT", "character varying": "TEXT",
    "char": "TEXT", "character": "TEXT", "citext": "TEXT",
    "boolean": "INTEGER", "bool": "INTEGER",
    "timestamptz": "TEXT", "timestamp with time zone": "TEXT",
    "timestamp": "TEXT", "timestamp without time zone": "TEXT",
    "date": "TEXT", "time": "TEXT", "time with time zone": "TEXT",
    "time without time zone": "TEXT", "interval": "TEXT",
    "numeric": "REAL", "decimal": "REAL", "money": "REAL",
    "real": "REAL", "double precision": "REAL",
    "smallint": "INTEGER", "integer": "INTEGER", "int": "INTEGER", "int2": "INTEGER",
    "int4": "INTEGER", "int8": "INTEGER", "bigint": "INTEGER",
    "json": "TEXT", "jsonb": "TEXT",
    "bytea": "BLOB",
    "inet": "TEXT", "cidr": "TEXT", "macaddr": "TEXT", "xml": "TEXT",
    "serial": "INTEGER", "bigserial": "INTEGER", "smallserial": "INTEGER",
    "tsvector": "TEXT", "tsquery": "TEXT", "hstore": "TEXT", "ltree": "TEXT",
    "name": "TEXT", "oid": "INTEGER",
}
STOP = {"not", "null", "default", "primary", "unique", "check", "references",
        "generated", "always", "collate", "constraint", "identity", "stored",
        "array", "deferrable", "initially"}
TBL_CONSTRAINT = {"constraint", "primary", "unique", "check", "foreign", "exclude", "like"}
DEFAULT_OK = re.compile(
    r"^(?:'[^']*'|-?\d+(?:\.\d+)?|true|false|null|current_timestamp|current_date|current_time"
    r"|datetime\('now'\)|\(datetime\('now'\)\)|''|\"\")\s*$", re.I)
PG_CAST = re.compile(r"^(?P<lit>.+?)::[\w\s\[\]\"'.]+$")

def strip_cast(dv):
    """`'{}'::text[]` -> `'{}'`. A PG cast is meaningless in SQLite (the literal
    is already TEXT); SQLite cannot even parse `::`. Strips `::a::b` repeatedly."""
    out = dv
    for _ in range(3):
        m = PG_CAST.match(out.strip())
        if not m: break
        out = m.group("lit").strip()
    return out

def map_type(tok):
    """tok: the PG type expression, as a token list. -> (sqlite_type, list_of_notes)"""
    notes = []
    t = " ".join(" ".join(tok).split())
    arr = t.endswith("[]")
    if arr:
        t = t[:-2].strip(); notes.append("array->JSON TEXT")
    low = t.lower()
    if low.startswith("double precision"): low = "double precision"
    if low.startswith("timestamp"): low = ("timestamp with time zone"
                                          if "with time zone" in low else
                                          "timestamp without time zone" if "without time zone" in low
                                          else "timestamp")
    base = TYPE_MAP.get(low)
    if base is None:
        head = re.match(r"[A-Za-z_][\w ]*", t)
        base2 = TYPE_MAP.get((head.group(0) if head else "").strip().lower().replace("  ", " "))
        if base2 is None:
            notes.append("UNMAPPED(" + t + ")->TEXT")
            return "TEXT", notes
        base = base2
    if low in ("numeric", "decimal") and not arr: notes.append("exact->REAL(float64)")
    if low in ("timestamptz", "timestamp", "timestamp with time zone",
               "timestamp without time zone"): notes.append("ts->ISO8601 TEXT")
    return base, notes

def parse_table(sql, real, start, endpos):
    head = sql[start:endpos]
    m = re.search(r"CREATE\s+(?:UNLOGGED\s+|TEMP\s+|TEMPORARY\s+)*TABLE\s+"
                  r"(?:IF\s+NOT\s+EXISTS\s+)?(?:([A-Za-z_][\w$]*)\s*\.\s*)?"
                  r"([A-Za-z_][\w$]*)\s*\(", head, re.I | re.S)
    if not m: return None
    schema = (m.group(1) or "public").replace('"', "")
    name = m.group(2).replace('"', "")
    b, _ = body(sql, start)
    b = " ".join(b.split())
    cols, tbl_pk, uniques, dropped = [], [], [], []
    for item in split_top(b):
        item = item.strip()
        if not item: continue
        low = item.lower()
        first = re.match(r"[A-Za-z_][\w]*", item)
        if not first: continue
        kw = first.group(0).lower()
        if kw in TBL_CONSTRAINT:
            pm = re.match(r"PRIMARY\s+KEY\s*\(([^)]*)\)", item, re.I | re.S)
            if pm: tbl_pk = [c.strip().strip('"') for c in pm.group(1).split(",")]
            um = re.match(r"UNIQUE\s*\(([^)]*)\)", item, re.I | re.S)
            if um: uniques.append([c.strip().strip('"') for c in um.group(1).split(",")])
            dropped.append(("constraint", kw.upper(), " ".join(item.split())[:160]))
            continue
        toks = item.split()
        cname = toks[0].strip('"')
        i = 1; tbuf = []
        while i < len(toks) and toks[i].lower() not in STOP:
            tbuf.append(toks[i]); i += 1
        rest = " ".join(toks[i:])
        stype, notes = map_type(tbuf or ["text"])
        seg = ["  " + cname + " " + stype]
        rl = rest.lower()
        pk = bool(re.search(r"\bPRIMARY\s+KEY\b", rl))
        if "GENERATED" in rl or "IDENTITY" in rl:
            notes.append("identity/serial->rowid"); pk = True
        if re.search(r"\bNOT\s+NULL\b", rl):
            seg.append("NOT NULL")
        dm = re.search(r"\bDEFAULT\s+(\S.*?)(?=\s+NOT\s+NULL\b|\s+PRIMARY\s+KEY\b|\s+UNIQUE\b|\s+CHECK\b|\s+REFERENCES\b|$)", rest, re.I | re.S)
        if dm:
            dv = strip_cast(" ".join(dm.group(1).split()))
            if dv.lower().startswith("nextval("): notes.append("DEFAULT nextval->dropped")
            elif DEFAULT_OK.match(dv): seg.append("DEFAULT " + dv)
            else: notes.append("DEFAULT dropped(" + dv[:60] + ")")
        if pk: seg.append("PRIMARY KEY")
        elif re.search(r"\bUNIQUE\b", rl): seg.append("UNIQUE")
        if "REFERENCES" in rl: notes.append("FK->not emitted (SQLite FKs off by default)")
        if re.search(r"\bCHECK\b", rl): notes.append("CHECK->dropped")
        cols.append({"name": cname, "pg": " ".join(tbuf) or "text", "sqlite": stype,
                     "line": " ".join(seg), "pk": pk, "notes": notes})
    return {"schema": schema, "name": name, "cols": cols, "tbl_pk": tbl_pk,
            "uniques": uniques, "dropped": dropped}

def main():
    with open(CORPUS, encoding="utf-8") as f:
        src = f.read()
    offs = []
    with open(MANIFEST, encoding="utf-8") as f:
        for line in f:
            p = line.rstrip("\n").split("\t")
            if len(p) >= 2: offs.append((int(p[0]), p[1]))
    offs.sort()
    def file_of(pos):
        f = None
        for o, nm in offs:
            if o <= pos: f = nm
            else: break
        return f or "(pre)"
    real = mask(src)
    clean = blank_comments(src)
    tables, order, seen_stmt = {}, [], set()
    tbl_re = re.compile(
        r"CREATE\s+(?:UNLOGGED\s+|TEMP\s+|TEMPORARY\s+)*TABLE\s+(?:IF\s+NOT\s+EXISTS\s+)?"
        r"(?:([A-Za-z_][\w$]*)\s*\.\s*)?([A-Za-z_][\w$]*)\s*\(", re.I | re.S)
    hits = [m for m in tbl_re.finditer(src) if real[m.start()]]
    print("create_table_statements =", len(hits))
    for m in hits:
        t = parse_table(clean, real, m.start(), m.end())
        if not t: continue
        key = t["name"]
        if key in tables:  # re-declared: merge late ALTERs already applied; keep first DDL
            tables[key]["redeclared"] = tables[key].get("redeclared", 0) + 1
            continue
        t["file"] = file_of(m.start())
        tables[key] = t; order.append(key)
    # ---- ALTER TABLE: ADD/DROP COLUMN (incl. multi-part), RENAME, ALTER COLUMN
    # Load-bearing: a multi-part ALTER carries a verb per part
    # (`ADD COLUMN a int, ADD COLUMN b int`), so only part 1 inherits the
    # statement verb. Missing that silently drops columns; and a multi-part
    # DROP list left as-is invents phantom columns named after the verb.
    PART = re.compile(r"^\s*(ADD|DROP)\s+(COLUMN|CONSTRAINT)\s+(IF\s+(?:NOT\s+)?EXISTS\s+)?(.+)$",
                      re.I | re.S)
    def parts_of(payload, inherit_column=True):
        out = []
        for raw in split_top(payload):
            raw = " ".join(raw.split())
            if not raw: continue
            m = PART.match(raw)
            if m:
                out.append((m.group(1).upper(), m.group(2).upper(), m.group(4)))
            elif inherit_column:
                out.append((None, None, raw))   # inherits the statement verb
        return out

    added = dropped_cols = renamed = relaxed = 0
    alt_re = re.compile(
        r"ALTER\s+TABLE\s+(?:IF\s+EXISTS\s+|ONLY\s+)?([\w$\.]+)\s+(.+?);", re.I | re.S)
    for m in alt_re.finditer(clean):
        if not real[m.start()]: continue
        key = m.group(1).replace('"', "").split(".")[-1]
        if key not in tables: continue
        stmt = " ".join(m.group(2).split())
        sm = re.match(r"^(ADD|DROP|RENAME|ALTER)\b(.*)$", stmt, re.I | re.S)
        if not sm: continue
        verb, rest = sm.group(1).upper(), sm.group(2).strip()
        # `ADD CONSTRAINT chk_x CHECK (...)` is a constraint, not a column.
        # Without this guard the constraint NAME is read as a column type and
        # 82 real statements invent 40 phantom columns. Measured.
        if verb in ("ADD", "DROP") and re.match(r"^CONSTRAINT\b", rest, re.I):
            continue
        # Strip the statement's own `COLUMN [IF [NOT] EXISTS]` prefix so that part 1
        # is a bare column spec and parts 2+ carry their own (stripped by PART).
        stmt_is_column = False
        cm = re.match(r"^COLUMN\s+(?:IF\s+(?:NOT\s+)?EXISTS\s+)?", rest, re.I)
        if cm:
            stmt_is_column = True
            rest = rest[cm.end():]
        elif not re.match(r"^(ADD|DROP)\b", rest, re.I):
            stmt_is_column = False

        if verb == "RENAME":
            rm = re.match(r"^TO\s+([\w$]+)$", rest, re.I)
            if rm:
                new_name = rm.group(1).replace('"', "")
                if new_name in tables:
                    # The stream really does bring the same name back twice
                    # (`…_partitioned` then `…_new` -> daily_snapshots). PG applies
                    # in order, so the LAST definition wins; recording the collision
                    # keeps the loss visible instead of silently double-counting it.
                    tables[new_name].setdefault("name_collisions", []).append(key)
                    tables[new_name]["renamed_from"] = key
                    tables.pop(key, None)
                    order[:] = [n for n in order if n != key]
                else:
                    tables[new_name] = tables.pop(key)
                    order[order.index(key)] = new_name
                    tables[new_name]["renamed_from"] = key
                renamed += 1
            continue
        if verb == "ALTER":
            # `ALTER COLUMN c DROP NOT NULL` relaxes a constraint; keeping the
            # NOT NULL would make D1 reject rows Postgres accepts.
            for am in re.finditer(r"ALTER\s+COLUMN\s+([\w$]+)\s+DROP\s+NOT\s+NULL", rest, re.I):
                for c in tables[key]["cols"]:
                    if c["name"] == am.group(1).replace('"', ""):
                        c["line"] = re.sub(r"\s+NOT NULL\b", "", c["line"])
                        c.setdefault("notes", []).append("NOT NULL dropped by later ALTER")
                        relaxed += 1
            continue

        for pverb, pwhat, payload in parts_of(rest, stmt_is_column):
            pv = pverb or verb
            if pv == "ADD" and (pwhat or "COLUMN") == "COLUMN":
                toks = payload.split()
                if not toks: continue
                cname = toks[0].strip('"'); i2 = 1; tbuf = []
                while i2 < len(toks) and toks[i2].lower() not in STOP:
                    tbuf.append(toks[i2]); i2 += 1
                r2 = " ".join(toks[i2:])
                if any(c["name"] == cname for c in tables[key]["cols"]): continue
                stype, notes = map_type(tbuf or ["text"])
                seg = ["  " + cname + " " + stype]
                if re.search(r"\bNOT\s+NULL\b", r2, re.I): seg.append("NOT NULL")
                dm = re.search(r"\bDEFAULT\s+(\S.*?)(?=\s+NOT\s+NULL\b|\s+PRIMARY\s+KEY\b|"
                               r"\s+UNIQUE\b|\s+CHECK\b|\s+REFERENCES\b|\s+CONSTRAINT\b|$)",
                               r2, re.I | re.S)
                if dm:
                    dv = strip_cast(" ".join(dm.group(1).split()))
                    if dv.lower().startswith("nextval("): notes.append("DEFAULT nextval->dropped")
                    elif DEFAULT_OK.match(dv): seg.append("DEFAULT " + dv)
                    else: notes.append("DEFAULT dropped(" + dv[:50] + ")")
                if re.search(r"\bUNIQUE\b", r2, re.I) and not re.search(r"\bCHECK\b", r2, re.I):
                    seg.append("UNIQUE")
                if re.search(r"\bREFERENCES\b", r2, re.I): notes.append("FK->not emitted")
                if re.search(r"\bCHECK\b", r2, re.I): notes.append("CHECK->dropped")
                tables[key]["cols"].append({"name": cname, "pg": " ".join(tbuf) or "text",
                                            "sqlite": stype, "line": " ".join(seg),
                                            "pk": False, "notes": notes})
                tables[key]["altered"] = tables[key].get("altered", 0) + 1
                added += 1
            elif pv == "DROP" and (pwhat or "COLUMN") == "COLUMN":
                cn = payload.split()[0].strip('"')
                tables[key]["cols"] = [c for c in tables[key]["cols"] if c["name"] != cn]
                tables[key].setdefault("dropped_cols", []).append(cn)
                dropped_cols += 1
    print("alter_added_columns =", added)
    print("alter_dropped_cols  =", dropped_cols)
    print("tables_renamed      =", renamed)
    print("not_null_relaxed    =", relaxed)
    print("order_unique        =", len(order), "of", len(set(order)))
    coll = {k: v.get("name_collisions") for k, v in tables.items() if v.get("name_collisions")}
    print("name_collisions     =", len(coll), coll)
    with open(os.path.join(WORK, "parsed.json"), "w") as f:
        json.dump({"tables": tables, "order": order}, f, indent=1)
    print("tables_parsed      =", len(order))
    print("redeclared         =", sum(t.get("redeclared", 0) for t in tables.values()))
    print("total_columns      =", sum(len(t["cols"]) for t in tables.values()))
    print("tables_with_no_pk  =", sum(1 for k in order if not tables[k]["tbl_pk"]
                                      and not any(c["pk"] for c in tables[k]["cols"])))
    print("composite_pk       =", sum(1 for k in order if tables[k]["tbl_pk"]))
    print("unmapped_types     =", sorted({n for t in tables.values() for c in t["cols"]
                                          for n in c["notes"] if n.startswith("UNMAPPED")}))
    notes = {}
    for t in tables.values():
        for c in t["cols"]:
            for n in c["notes"]:
                key = re.sub(r"\(.*?\)", "(...)", n)
                notes[key] = notes.get(key, 0) + 1
    print("notes:")
    for k in sorted(notes, key=lambda x: -notes[x]): print("   %-58s %d" % (k, notes[k]))

main()

with open(os.path.join(WORK, "parsed.json")) as f:
    d = json.load(f)
tables, order = d["tables"], d["order"]

DOMAIN = [
    (r"^portfolio_ledger_", "portfolio_ledger"),
    (r"^olympus_",           "olympus"),
    (r"^(position|nav_history|price_history|fx_|trade|cash|account|broker|"
     r"decision|thesis|document|workspace|benchmark|risk|metric|signal|"
     r"alert|notification|research|knowledge|product|stripe|instrument|"
     r"house|custodian|macro|news|sentiment|backtest|allocation)", "core"),
]
def domain_of(n):
    for rx, d_ in DOMAIN:
        if re.match(rx, n): return d_
    return "core"

buckets = {}
for k in order:
    buckets.setdefault(domain_of(k), []).append(k)

MARKER = """-- {name}
-- Generated by apps/dashboard-api/d1-local/generate_d1_schema.py (DIG-2891).
-- Source of truth: digiquant/supabase/migrations/*.sql on develop.
-- Schema only. No data, no seed, no Supabase access, no Cloudflare prod binding.
-- {n} tables. Applying this file is idempotent.

"""

def marker_insert(version, note):
    return (
        "INSERT INTO d1_local_schema_version (version, applied_at, note)\n"
        "SELECT {v}, datetime('now'), '{n}'\n"
        "WHERE NOT EXISTS (SELECT 1 FROM d1_local_schema_version WHERE version = {v});\n"
    ).format(v=version, n=note)

ver = 1
written = []
for dom in sorted(buckets):
    names = sorted(buckets[dom])
    CH = 12
    for ci in range(0, len(names), CH):
        chunk = names[ci:ci + CH]
        ver += 1
        fn = "%04d_%s_%02d.sql" % (ver, dom, ci // CH + 1)
        parts = [MARKER.format(name=fn, n=len(chunk))]
        for t in chunk:
            tb = tables[t]
            cols = tb["cols"]
            if not cols:
                continue
            segs = [c["line"] for c in cols]
            # Composite PRIMARY KEY and table-level UNIQUE live outside the
            # column list in PG; SQLite accepts both inline, and dropping them
            # would silently strip uniqueness from 14 tables.
            if tb["tbl_pk"]:
                segs.append("  PRIMARY KEY (%s)" % ", ".join(tb["tbl_pk"]))
            for uq in tb["uniques"]:
                segs.append("  UNIQUE (%s)" % ", ".join(uq))
            parts.append("CREATE TABLE IF NOT EXISTS %s (\n%s\n);\n"
                         % (t, ",\n".join(segs)))
        parts.append(marker_insert(ver, "DIG-2891 %s: %d tables" % (dom, len(chunk))))
        with open(os.path.join(OUT, fn), "w") as fh:
            fh.write("\n".join(parts))
        written.append((fn, len(chunk)))

print("files_written =", len(written))
print("tables_covered =", sum(n for _, n in written), "of", len(order))
# residual unmapped, for adjudication
bad = [(t, c["name"], c["pg"]) for t in order for c in tables[t]["cols"]
       if any(n.startswith("UNMAPPED") for n in c["notes"])]
print("unmapped_remaining =", len(bad))
for t, c, pg in bad:
    print("   %-42s %-22s %r" % (t, c, pg[:60]))
print("files_written      =", len(written))
print("out_dir            =", OUT)
if not ARGS.keep_corpus:
    shutil.rmtree(WORK, ignore_errors=True)
else:
    print("corpus_kept        =", WORK)
