#!/usr/bin/env python3
"""Assert staged macro CSVs meet full-depth floors (credentialed-env gate, #4804).

Exits 0 if every series passes; exits 1 listing gaps (series, have-first-date,
need-first-date, have-rows, need-rows). The gold gate (Plan 4 Task 3) consumes
this exit code: hy/ig stay at weight 0 until this passes.

Floor calibration note: the first-date floors below are the actual FRED
first-observation dates (first trading day / first weekly print), NOT month
starts. Month-start approximations (e.g. "2008-06-01" for GVZCLS, whose first
print is 2008-06-03) false-positive on full-depth staging under the strict
``have > need`` comparison, so the verifier would never reach exit 0 even
after a correct credentialed re-stage. Row floors are unchanged.
"""

from __future__ import annotations

import json
from pathlib import Path

import polars as pl

ROOT = Path(__file__).resolve().parents[1]
STAGING = ROOT / "data" / "price-history"

FLOORS: dict[str, dict] = {
    "M2SL": {"first": "1959-01-01", "rows": 700},
    "DTWEXBGS": {"first": "2006-01-02", "rows": 5000},
    "GVZCLS": {"first": "2008-06-03", "rows": 4000},
    "WALCL": {"first": "2002-12-18", "rows": 1000},
    "BAMLH0A0HYM2": {"first": "1996-12-31", "rows": 7000},
    "BAMLC0A0CM": {"first": "1996-12-31", "rows": 7000},
    "T5YIE": {"first": "2003-01-02", "rows": 5000},
    "NFCI": {"first": "1971-01-08", "rows": 2500},
}

FRED_STARTS: dict[str, str] = {  # full-history start per FRED (approx, for the handoff note)
    "BAMLH0A0HYM2": "1996-12-31",
    "BAMLC0A0CM": "1996-12-31",
}


def main() -> int:
    gaps = []
    for series, floor in FLOORS.items():
        path = STAGING / f"{series}.csv"
        if not path.is_file():
            gaps.append({"series": series, "missing": True})
            continue
        frame = pl.read_csv(path)
        first = str(frame["observation_date"].to_list()[0])[:10]
        rows = len(frame)
        if first > floor["first"] or rows < floor["rows"]:
            gaps.append(
                {
                    "series": series,
                    "have_first": first,
                    "need_first": floor["first"],
                    "have_rows": rows,
                    "need_rows": floor["rows"],
                }
            )
    if gaps:
        print(json.dumps({"depth_ok": False, "gaps": gaps}, indent=2))
        return 1
    print(json.dumps({"depth_ok": True}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
