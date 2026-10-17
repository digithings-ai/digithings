# Gold macro depth re-stage handoff (#4804)

## (a) Why the FRED-API version is dead

#4794 PR3 (`00dfc4b6c`) dropped the last FRED observations-API / fredgraph
callers; the rebased `export_sdca_macro.export_series` cascade is supabase →
sealed R2 only, keyless. Any procedure keyed on `FRED_API_KEY` is dead — do
not run it, here or anywhere.

## (b) Re-stage commands (run where creds exist)

```bash
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/export_sdca_macro.py --cache-dir digiquant/data/price-history --series BAMLH0A0HYM2,BAMLC0A0CM
PYTHONPATH=digiquant/src .venv/bin/python digiquant/scripts/verify_macro_depth.py; echo "exit=$?"
```

Only the two BAML series need re-staging; the other six staged CSVs are
already full-depth (verifier passes them — see gap JSON below).

## (c) Env required (names quoted from code, verified by reading)

First-hit tier — Supabase (`digiquant/scripts/export_sdca_macro.py:76-82`,
`rows_from_supabase`):

- URL: `CORE_SUPABASE_URL` or `SUPABASE_URL`
- Key: `CORE_SUPABASE_SERVICE_KEY` or `SUPABASE_SERVICE_ROLE_KEY` or
  `SUPABASE_SERVICE_KEY` (table: `macro_series_observations`)

Second tier — sealed R2 (`digiquant/scripts/export_sdca_macro.py:120-136`,
`rows_from_r2`; constant values from
`digiquant/src/digiquant/ops/checkpoint_archive.py:1005-1008`):

- `R2_ACCOUNT_ID`, `R2_BUCKET`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`
  (reads the `fred__{series_id}` generation via `MANIFEST_KEY`)

Either tier suffices (first hit wins); fredgraph alone is NOT sufficient —
it truncates BAML to a ~3y window (785 rows from 2023-09-30).

## (d) Expected post-fix bounds

- BAMLH0A0HYM2 / BAMLC0A0CM from ~1996-12-31, ~7500 rows
  (verifier floors: first `1996-12-31`, rows `7000`).
- Verifier exit 0 (`{"depth_ok": true}`).
- Never present fredgraph-tier output as full-depth.

## (e) Standing gap JSON (2026-09-30, re-verified this run, exit=1)

```json
{
  "depth_ok": false,
  "gaps": [
    {
      "series": "BAMLH0A0HYM2",
      "have_first": "2023-09-30",
      "need_first": "1996-12-31",
      "have_rows": 785,
      "need_rows": 7000
    },
    {
      "series": "BAMLC0A0CM",
      "have_first": "2023-09-30",
      "need_first": "1996-12-31",
      "have_rows": 784,
      "need_rows": 7000
    }
  ]
}
```

Context: BAML pair still truncated here; GVZ/NFCI have no refresh path
anywhere (upstream catalog misses, Task-2 probes), and DXY (DTWEXBGS) is off
the panel — so even after this re-stage, GVZ/NFCI/DXY legs stay frozen
snapshots. Until the verifier exits 0, hy/ig stay at weight 0.

## (f) Follow-up triggers

- Verifier exit 0 → re-run the Task-1 duel to re-confirm the winner on
  full-depth BAML, then a Task-3-class gate with hy/ig at the duel winner's
  weight — a NEW plan, not this one.
- Verifier exit 1 with fewer gaps → report the new gap set, no scope
  expansion here.

## Self-test record (2026-09-30, uncredentialed env — proves §(c) accurate)

Re-stage attempted HERE; failed at the credential tier exactly as expected
(zero `R2_*` / `SUPABASE_*` / `CORE_SUPABASE_*` vars set; supabase tier
returned `[]`, R2 tier returned `[]`):

```
RuntimeError: no observations for BAMLH0A0HYM2 from supabase or sealed R2
exit=1
```

Staged CSVs untouched (failure raises before any write). Verifier re-run
after the attempt returns the §(e) gap set unchanged, exit 1.
