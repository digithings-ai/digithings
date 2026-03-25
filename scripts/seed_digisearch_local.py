#!/usr/bin/env python3
"""Seed DigiSearch by POSTing files from digisearch/seeds to /ingest.

Requires a DigiKey-issued API key with digisearch:ingest (or *).

Examples:
  DIGISEARCH_SEED_API_KEY=dgk_live_... python scripts/seed_digisearch_local.py

  # DigiSearch runs in Docker (seeds copied to /app/digisearch/seeds in image):
  DIGISEARCH_SEED_REMOTE_PREFIX=/app/digisearch/seeds DIGISEARCH_URL=http://127.0.0.1:8002 \\
    DIGISEARCH_SEED_API_KEY=dgk_live_... python scripts/seed_digisearch_local.py
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path


def _post_json(url: str, payload: dict, headers: dict[str, str]) -> dict:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise SystemExit(f"HTTP {e.code} {url}: {detail}") from e


def _oauth_token(digikey_url: str, api_key: str) -> str:
    base = digikey_url.rstrip("/")
    out = _post_json(
        f"{base}/v1/oauth/token",
        {"grant_type": "api_key", "api_key": api_key},
        headers={},
    )
    token = out.get("access_token")
    if not token:
        raise SystemExit(f"No access_token in DigiKey response: {out}")
    return str(token)


def main() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument(
        "--digikey-url",
        default=os.environ.get("DIGIKEY_URL", "http://127.0.0.1:8005"),
    )
    ap.add_argument(
        "--digisearch-url",
        default=os.environ.get("DIGISEARCH_URL", "http://127.0.0.1:8002"),
    )
    ap.add_argument(
        "--api-key",
        default=os.environ.get("DIGISEARCH_SEED_API_KEY", ""),
        help="dgk_live_... with digisearch:ingest (or env DIGISEARCH_SEED_API_KEY)",
    )
    ap.add_argument(
        "--index",
        default=os.environ.get("DIGISEARCH_INDEX", "default"),
    )
    ap.add_argument(
        "--seeds-dir",
        type=Path,
        default=repo_root / "digisearch" / "seeds",
        help="Local directory to list seed files (names drive remote paths when using --remote-prefix)",
    )
    ap.add_argument(
        "--remote-prefix",
        default=os.environ.get("DIGISEARCH_SEED_REMOTE_PREFIX", "").strip() or None,
        metavar="PREFIX",
        help="If set (e.g. /app/digisearch/seeds), source path sent to API is PREFIX/basename",
    )
    args = ap.parse_args()
    key = (args.api_key or "").strip()
    if not key:
        ap.print_help()
        raise SystemExit("Missing API key: pass --api-key or set DIGISEARCH_SEED_API_KEY")

    seeds_dir: Path = args.seeds_dir
    if not seeds_dir.is_dir():
        raise SystemExit(f"Not a directory: {seeds_dir}")

    token = _oauth_token(args.digikey_url, key)
    base = args.digisearch_url.rstrip("/")
    auth = {"Authorization": f"Bearer {token}"}

    skip = {".gitkeep", "readme.md"}
    files = sorted(
        p
        for p in seeds_dir.iterdir()
        if p.is_file() and not p.name.startswith(".") and p.name.lower() not in skip
    )
    if not files:
        raise SystemExit(f"No files under {seeds_dir}")

    for path in files:
        if args.remote_prefix:
            src = f"{args.remote_prefix.rstrip('/')}/{path.name}"
        else:
            src = str(path.resolve())
        payload = {"source": src, "index_name": args.index}
        out = _post_json(f"{base}/ingest", payload, auth)
        print(f"ingest {path.name} -> {out.get('status', 'ok')} chunks={out.get('chunks_created')} doc_id={out.get('doc_id')}")


if __name__ == "__main__":
    main()
