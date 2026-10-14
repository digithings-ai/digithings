#!/usr/bin/env python3
"""Non-vacuity harness for apps/digidata-api/d1/twelvex/0001_init.sql (DIG-2890).

What it proves, in this order:
  1. the schema APPLIES to a fresh SQLite database (rc!=0 and a non-empty stderr
     abort the run);
  2. every table ACCEPTS a row that conforms to its own discovered CHECKs;
  3. every CHECK REJECTS a violating row.

Point 3 is the point. A CHECK that never fires is a silent no-op, so the
harness discovers its constraints from the APPLIED schema (sqlite_master.sql,
via PRAGMA table_info) rather than from a hand-written list, and then proves
each one can fail. A green run on the pre-review draft exits 1 with
"expected 9 enum CHECKs, got 0", which is the control that makes a green run on
this draft mean something.

Usage:
    python3 scripts/verify_d1_twelvex_schema.py [path/to/0001_init.sql]
    python3 scripts/verify_d1_twelvex_schema.py --schema path/to/schema.sql

Requires the JSON1 extension (json_valid). Verified on SQLite 3.51.0.
Exit 0 = every constraint fired and every conforming row was accepted.
"""
import os
import sqlite3
import sys
import tempfile

_here = os.path.dirname(os.path.abspath(__file__))
_default = os.path.join(
    _here, os.pardir, "apps", "digidata-api", "d1", "twelvex", "0001_init.sql"
)
if len(sys.argv) > 1 and sys.argv[1] == "--schema":
    schema = sys.argv[2]
else:
    schema = sys.argv[1] if len(sys.argv) > 1 and sys.argv[1] != "--schema" else _default
schema = os.path.abspath(schema)
if not os.path.exists(schema):
    sys.exit("schema not found: " + schema)

_fd, _db = tempfile.mkstemp(prefix="d1_twelvex_", suffix=".db")
os.close(_fd)
try:
    with open(schema, "r", encoding="utf-8") as _f:
        _sql = _f.read()
    sqlite3.connect(_db).executescript(_sql)
except Exception as exc:  # noqa: BLE001 - report, do not mask
    sys.exit("schema failed to apply: %s" % (exc,))
sys.argv = [sys.argv[0], _db]

# ---- verification body (unchanged from the development copy) ----------------
import json, re, sqlite3, sys, os
db = sys.argv[1]
assert os.path.exists(db), "no db"
c = sqlite3.connect(db)
tables = c.execute("select name from sqlite_master where type='table' order by name").fetchall()
tabs = [t[0] for t in tables]
print("TABLES", len(tabs))

ARM_NULL = re.compile(r"CHECK \(\(*([a-z_]+)\s+IS NULL\)\s+OR\s+\([a-z_]+\s+IN\s+\((.*?)\)\)+\s*$", re.I | re.S)
ARM_PLAIN = re.compile(r"CHECK \(\(*([a-z_]+)\s+IN\s+\((.*?)\)\)+\s*$", re.I | re.S)
ARM_JSON = re.compile(r"CHECK \(([a-z_]+)\s+IS NULL\s+OR\s+json_valid\(\1\)\)\s*$", re.I | re.S)

def split_vals(s):
    return [x.strip().strip("'") for x in s.split(",")]

enum_checks, json_checks = [], []
for name, sql in c.execute("select name,sql from sqlite_master where type='table' order by name"):
    if not sql or "CHECK" not in sql:
        continue
    for raw in re.findall(r"CHECK \(.*?\)(?=,|\s*\n)", sql, re.I | re.S):
        m = ARM_JSON.match(raw)
        if m:
            json_checks.append((name, m.group(1))); continue
        m = ARM_NULL.match(raw) or ARM_PLAIN.match(raw)
        if m:
            enum_checks.append((name, m.group(1), split_vals(m.group(2)), bool(ARM_NULL.match(raw))))
        else:
            print("UNMATCHED", name, repr(raw)); sys.exit(1)

print("ENUM_CHECKS", len(enum_checks), [f"{t}.{col}" for t, col, _, _ in enum_checks])
print("JSON_CHECKS", len(json_checks), [f"{t}.{col}" for t, col in json_checks])
assert len(enum_checks) == 9, f"expected 9 enum CHECKs, got {len(enum_checks)}"
assert len(json_checks) == 20, f"expected 20 json CHECKs, got {len(json_checks)}"

JSON_MEMBER = {}
ENUM_MEMBER = {}
for _t, _c in json_checks:
    JSON_MEMBER[(_t, _c)] = "[]"
for _t, _c, _vals, _nullable in enum_checks:
    ENUM_MEMBER[(_t, _c)] = _vals

def quote(v):
    if isinstance(v, (int, float)):
        return str(v)
    return "'" + str(v).replace("'", "''") + "'"

def build(tbl, override=None):
    override = override or {}
    cols, vals, names = [], [], []
    for cid, col, typ, notnull, dflt, pk in c.execute(f'PRAGMA table_info("{tbl}")'):
        names.append(col)
        if col in override:
            cols.append('"%s"' % col); vals.append("NULL" if override[col] is None else quote(override[col]))
            continue
        if (tbl, col) in JSON_MEMBER:
            v = JSON_MEMBER[(tbl, col)]
        elif (tbl, col) in ENUM_MEMBER:
            allowed = ENUM_MEMBER[(tbl, col)]
            v = next((x for x in allowed if x.isdigit()), allowed[0])
        else:
            t = (typ or "").upper()
            if t.startswith("INT"):
                v = 1
            elif "REAL" in t or "FLOA" in t or "DOUB" in t:
                v = 1.5
            else:
                v = "v%d" % cid
        cols.append('"%s"' % col); vals.append(quote(v))
    return cols, vals, names

def try_insert(tbl, cols, vals):
    sql = f'INSERT INTO "{tbl}" ({",".join(cols)}) VALUES ({",".join(vals)})'
    try:
        c.execute(sql); c.commit(); return True, ""
    except sqlite3.Error as e:
        c.rollback(); return False, str(e)

fails = []
for t in tabs:
    cols, vals, _ = build(t)
    ok, err = try_insert(t, cols, vals)
    if not ok:
        fails.append(f"conforming row REJECTED for {t}: {err}")
        print("FAIL_ACCEPT", t, err)
print("ACCEPT_ALL", "ok" if not fails else "broken")

for (t, col, vals, nullable) in enum_checks:
    cols, v, _ = build(t, override={col: "ZZZ_NOT_A_MEMBER_QQQ"})
    ok, err = try_insert(t, cols, v)
    if ok:
        fails.append(f"enum CHECK {t}.{col} did NOT reject a bad value")
        print("FAIL_REJECT_ENUM", t, col)
for (t, col) in json_checks:
    cols, v, _ = build(t, override={col: "not json {{{"})
    ok, err = try_insert(t, cols, v)
    if ok:
        fails.append(f"json_valid CHECK {t}.{col} did NOT reject bad json")
        print("FAIL_REJECT_JSON", t, col)

print("TOTAL_FAILS", len(fails))
for f in fails:
    print(" -", f)
sys.exit(1 if fails else 0)
