"""Small public market-data slice into local R2 (plan section 5).

Layout parity is *structural*, not asserted: every key and every manifest
field is imported from the production writer
(:mod:`digiquant.data.prices.r2_history`) and the parquet bytes are produced
by the production encoder
(:func:`scripts.backfill_market_data_r2.to_parquet_bytes`). If either ever
changes shape, this seeder changes with it instead of drifting.

The reader the local stack exercises is
``apps/digithings-stack-cloudflare/src/market-data.ts``: it reads
``market-data/manifest.json``, requires each dataset entry to carry both
``object`` and ``sha256``, verifies sha256 over the object bytes (502 on
mismatch) and projects ``date``/``ticker``/``close`` with hyparquet.

Idempotency: objects are content-addressed by ``as_of`` and the manifest is
a deterministic function of the generated rows, so re-running writes the same
keys with the same digests.
"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from datetime import date
from typing import Any

from scripts.seed.deterministic import digest, synthetic_ohlc

#: Small, deliberately: enough to render charts and exercise the R2 seam.
DEFAULT_TICKERS: tuple[str, ...] = ("SPY", "QQQ", "TLT", "GLD")
DEFAULT_DAYS = 260
DEFAULT_AS_OF = date(2026, 10, 9)


@dataclass(frozen=True)
class R2Object:
    """One object to put into R2: key plus exact bytes."""

    key: str
    payload: bytes
    content_type: str

    @property
    def sha256(self) -> str:
        return digest(self.payload)


def build_market_slice(
    *,
    seed: int,
    tickers: tuple[str, ...] = DEFAULT_TICKERS,
    days: int = DEFAULT_DAYS,
    as_of: date = DEFAULT_AS_OF,
) -> list[R2Object]:
    """Build the manifest + one parquet generation per ticker, deterministically.

    Returns objects in put order: generations, then ``latest`` pointers,
    then the manifest last so a reader never sees a manifest pointing at an
    object that is not there yet.
    """
    from digiquant.data.prices.r2_history import (  # imported late: needs digiquant src on path
        MANIFEST_KEY,
        SOURCE_TABLE_PRICE,
        build_manifest,
        generation_key,
        latest_pointer_key,
        normalize_ticker,
    )

    from scripts.backfill_market_data_r2 import to_parquet_bytes

    objects: list[R2Object] = []
    datasets: dict[str, Any] = {}
    for ticker in tickers:
        rows = synthetic_ohlc(ticker, days=days, seed=seed, start=as_of - _days_back(days))
        payload = to_parquet_bytes(rows, date_col="date")
        key = generation_key(ticker, as_of.isoformat())
        normalized = normalize_ticker(ticker)
        objects.append(
            R2Object(key=key, payload=payload, content_type="application/vnd.apache.parquet")
        )
        objects.append(
            R2Object(
                key=latest_pointer_key(ticker),
                payload=key.encode("utf-8"),
                content_type="text/plain",
            )
        )
        datasets[normalized] = {
            "object": key,
            "sha256": digest(payload),
            "rows": len(rows),
            "source_table": SOURCE_TABLE_PRICE,
            "as_of": as_of.isoformat(),
            "synthetic": True,
        }

    manifest = build_manifest(
        as_of=as_of.isoformat(),
        datasets=datasets,
        stale=False,
        # Fixed, not `now()`: a wall-clock stamp would make every run a
        # diff and break the digest a reader can verify.
        generated_at=f"{as_of.isoformat()}T00:00:00+00:00",
    )
    manifest["synthetic"] = True
    objects.append(
        R2Object(
            key=MANIFEST_KEY,
            payload=json.dumps(manifest, sort_keys=True).encode("utf-8"),
            content_type="application/json",
        )
    )
    return objects


def _days_back(days: int):
    from datetime import timedelta

    return timedelta(days=int(days * 1.6) + 20)


def put_local(objects: list[R2Object], *, bucket: str, persist_to: str | None = None) -> None:
    """Put *objects* into the LOCAL Miniflare R2 bucket via wrangler.

    ``--local`` is not optional: without it wrangler would write to the real
    bucket. There is no code path in this module that can write remotely.
    """
    import tempfile
    from pathlib import Path

    with tempfile.TemporaryDirectory(prefix="dt-seed-r2-") as tmp:
        for obj in objects:
            blob = Path(tmp) / obj.key.replace("/", "_")
            blob.write_bytes(obj.payload)
            cmd = [
                "wrangler",
                "r2",
                "object",
                "put",
                f"{bucket}/{obj.key}",
                "--file",
                str(blob),
                "--content-type",
                obj.content_type,
                "--local",
            ]
            if persist_to:
                cmd += ["--persist-to", persist_to]
            result = subprocess.run(cmd, capture_output=True, text=True, check=False)
            if result.returncode != 0:
                raise RuntimeError(
                    f"wrangler r2 put failed for {obj.key} (rc={result.returncode}): "
                    f"{(result.stderr or result.stdout).strip()[:400]}"
                )
