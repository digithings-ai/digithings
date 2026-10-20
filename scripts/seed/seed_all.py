#!/usr/bin/env python3
"""Run every local-stack seeder in dependency order (plan section 5 / §3 `dt seed`).

    python3 -m scripts.seed.seed_all --seed 42            # apply everything available
    python3 -m scripts.seed.seed_all --seed 42 --dry-run  # print the plan, write nothing

Deterministic: the same ``--seed`` produces the same synthetic values and
the same object digests on every run and every machine. Idempotent: every
step converges on re-run rather than accumulating rows or objects.

Synthetic only, and no production writes: each step that can write asserts a
loopback target first (see :func:`scripts.seed.deterministic.require_local`),
and no step reads client data. Steps whose backing service is not running
report `skipped` with the reason — they never fabricate a success.

Exit code 0 only when every step that ran succeeded.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import asdict, dataclass, field
from pathlib import Path

if __package__ in (None, ""):  # allow `python3 scripts/seed/seed_all.py`
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from scripts.seed.deterministic import DEFAULT_SEED

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_OUT_DIR = REPO_ROOT / ".digithings-local-seed"
STEPS = ("tenants", "portfolio", "digikey", "r2", "digisearch", "digigraph")


@dataclass
class StepResult:
    name: str
    status: str  # applied | skipped | failed
    detail: str = ""
    artifacts: list[str] = field(default_factory=list)
    digests: dict[str, str] = field(default_factory=dict)


def _env(name: str) -> str:
    value = os.environ.get(name, "")
    return value.strip()


def step_tenants(args, out: Path) -> StepResult:
    from scripts.seed import tenants
    from scripts.seed.portfolio import brief_documents

    docs = brief_documents(seed=args.seed)
    if args.dry_run:
        workspaces, members = tenants.rows(seed=args.seed)
        return StepResult(
            "tenants",
            "skipped",
            "dry-run",
            artifacts=[tenants.SUPABASE_SEED_SQL],
            digests={f"workspace:{w['slug']}": w["id"] for w in workspaces}
            | {f"member:{m['workspace_id']}/{m['user_id']}": m["user_id"] for m in members},
        )
    result = tenants.apply(
        seed=args.seed,
        supabase_url=_env("SUPABASE_URL") or None,
        service_key=_env("SUPABASE_SERVICE_ROLE_KEY") or None,
        documents=docs,
    )
    artifacts = []
    if result.action == "applied":
        path = out / "briefs.json"
        path.write_text(json.dumps(docs, sort_keys=True, indent=2) + "\n", encoding="utf-8")
        artifacts.append(str(path.relative_to(REPO_ROOT)))
    return StepResult("tenants", result.action, result.detail, artifacts)


def step_portfolio(args, out: Path) -> StepResult:
    """Delegate to the existing house demo seeder rather than redefine it."""
    if args.dry_run:
        return StepResult(
            "portfolio", "skipped", "dry-run", artifacts=["scripts/seed_digiquant_demo.py"]
        )
    if not (_env("SUPABASE_URL") and _env("SUPABASE_SERVICE_ROLE_KEY")):
        return StepResult(
            "portfolio", "skipped", "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set"
        )
    import subprocess

    cmd = [sys.executable, str(REPO_ROOT / "scripts" / "seed_digiquant_demo.py")]
    proc = subprocess.run(cmd, cwd=str(REPO_ROOT), check=False, capture_output=True, text=True)
    if proc.returncode != 0:
        return StepResult("portfolio", "failed", (proc.stderr or proc.stdout).strip()[:400])
    return StepResult("portfolio", "applied", "scripts/seed_digiquant_demo.py")


def step_digikey(args, out: Path) -> StepResult:
    from scripts.seed import digikey_keys
    from scripts.seed.portfolio import DEMO_TENANT_SLUG

    secret_file = out / "digikey-seed-keys.env"
    results = digikey_keys.ensure_keys(
        tenant_slug=DEMO_TENANT_SLUG,
        database_url=_env("DIGIKEY_DATABASE_URL") or None,
        out_path=secret_file,
        seed=args.seed,
    )
    # Only the prefix and length are ever reported; the raw value stays in the 0600 file.
    return StepResult(
        "digikey",
        "skipped" if all(r.action == "skipped" for r in results) else "applied",
        f"{sum(1 for r in results if r.action == 'minted')} minted, "
        f"{sum(1 for r in results if r.action == 'reused')} reused",
        artifacts=[rel(secret_file)] if secret_file.exists() else [],
        digests={r.label: r.key_prefix for r in results},
    )


def step_r2(args, out: Path) -> StepResult:
    from scripts.seed import r2_market

    objects = r2_market.build_market_slice(
        seed=args.seed, tickers=tuple(args.tickers), days=args.days
    )
    manifest = json.loads(objects[-1].payload.decode("utf-8"))
    path = out / "r2-manifest.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    artifacts = [rel(path)]
    if not args.dry_run and args.r2_bucket:
        r2_market.put_local(objects, bucket=args.r2_bucket, persist_to=args.persist_to)
        artifacts.append(f"miniflare-r2://{args.r2_bucket}")
    return StepResult(
        "r2",
        "skipped" if args.dry_run else "applied",
        f"{len(objects)} objects, {len(manifest['datasets'])} tickers, as_of={manifest['as_of']}",
        artifacts,
        digests={o.key: o.sha256 for o in objects},
    )


def step_digisearch(args, out: Path) -> StepResult:
    from scripts.seed import digikey_keys, digisearch

    docs = digisearch.corpus_documents(seed=args.seed)
    artifacts = [rel(p) for p, _ in docs]
    digests = {p.name: sha for p, sha in docs}
    if args.dry_run:
        return StepResult("digisearch", "skipped", "dry-run", artifacts, digests)
    env = digikey_keys.secret_file_env(out / "digikey-seed-keys.env")
    api_key = env.get("seed-ingest") or _env("DIGISEARCH_SEED_API_KEY")
    if not api_key:
        return StepResult(
            "digisearch",
            "skipped",
            "no digisearch-scoped key; run the digikey step first",
            artifacts,
            digests,
        )
    code = digisearch.run_ingest(
        api_key=api_key,
        digisearch_url=_env("DIGISEARCH_URL") or "http://127.0.0.1:8002",
        digikey_url=_env("DIGIKEY_URL") or "http://127.0.0.1:8005",
    )
    return StepResult(
        "digisearch",
        "applied" if code == 0 else "failed",
        f"ingest exit={code}",
        artifacts,
        digests,
    )


def step_digigraph(args, out: Path) -> StepResult:
    from scripts.seed import digigraph

    fixtures = digigraph.thread_fixtures(seed=args.seed)
    artifacts = [rel(p) for p, _ in fixtures]
    digests = {p.name: sha for p, sha in fixtures}
    return StepResult("digigraph", "applied", digigraph.load_status()["reason"], artifacts, digests)


def rel(path: Path) -> str:
    """Repo-relative path when possible, absolute otherwise.

    `--out-dir` may legitimately point outside the repository (a tmp dir in
    the tests, a scratch path on a workstation), and `Path.relative_to`
    raises rather than degrading — so never call it unguarded.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


DISPATCH = {
    "tenants": step_tenants,
    "portfolio": step_portfolio,
    "digikey": step_digikey,
    "r2": step_r2,
    "digisearch": step_digisearch,
    "digigraph": step_digigraph,
}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dt-seed", description=__doc__)
    parser.add_argument(
        "--seed", type=int, default=DEFAULT_SEED, help="deterministic seed (contract: 42)"
    )
    parser.add_argument("--out-dir", default=str(DEFAULT_OUT_DIR))
    parser.add_argument("--only", nargs="*", choices=STEPS, help="run only these steps")
    parser.add_argument("--skip", nargs="*", default=[], choices=STEPS)
    parser.add_argument("--tickers", nargs="*", default=["SPY", "QQQ", "TLT", "GLD"])
    parser.add_argument("--days", type=int, default=260)
    parser.add_argument(
        "--r2-bucket", default="", help="local Miniflare bucket; empty = build objects only"
    )
    parser.add_argument("--persist-to", default=None, help="wrangler --persist-to directory")
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    out = Path(args.out_dir)
    out.mkdir(parents=True, exist_ok=True)
    out.chmod(0o700)

    selected = [s for s in STEPS if (not args.only or s in args.only) and s not in args.skip]
    results: list[StepResult] = []
    for name in selected:
        try:
            results.append(DISPATCH[name](args, out))
        except Exception as exc:  # one broken step must not hide the others
            results.append(StepResult(name, "failed", f"{type(exc).__name__}: {exc}"[:400]))
        print(f"[{name}] {results[-1].status} {results[-1].detail}", flush=True)

    manifest = {
        "seed": args.seed,
        "synthetic": True,
        "dry_run": args.dry_run,
        "steps": [asdict(r) for r in results],
    }
    (out / "seed-manifest.json").write_text(
        json.dumps(manifest, sort_keys=True, indent=2) + "\n", encoding="utf-8"
    )
    failed = [r.name for r in results if r.status == "failed"]
    print(
        json.dumps(
            {
                "seed": args.seed,
                "failed": failed,
                "skipped": [r.name for r in results if r.status == "skipped"],
            }
        )
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
