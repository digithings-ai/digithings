"""Normative merge rule (§3.2): R2 wins for date <= manifest.as_of; live wins
only for manifest.as_of < date <= as_of; the live as_of-dated bar is excluded
unless sealed (settled-close semantics)."""

from __future__ import annotations

import hashlib

import polars as pl


def canonical_date(frame: pl.DataFrame) -> pl.DataFrame:
    return frame.with_columns(pl.col("date").cast(pl.Date).alias("date")).sort("date")


def apply_settled_close(frame: pl.DataFrame, as_of: str, sealed: bool) -> pl.DataFrame:
    """Drop the live ``as_of``-dated bar unless the close has settled (``sealed``)."""
    out = canonical_date(frame)
    if sealed:
        return out
    return out.filter(pl.col("date") < pl.lit(as_of).cast(pl.Date))


def merge_history_live(
    hist: pl.DataFrame, live: pl.DataFrame, manifest_as_of: str, as_of: str, sealed: bool
) -> pl.DataFrame:
    manifest_as_of_d = pl.lit(manifest_as_of).cast(pl.Date)
    as_of_d = pl.lit(as_of).cast(pl.Date)
    h = canonical_date(hist).filter(pl.col("date") <= manifest_as_of_d)
    live_window = canonical_date(live).filter(
        (pl.col("date") > manifest_as_of_d) & (pl.col("date") <= as_of_d)
    )
    live_window = apply_settled_close(live_window, as_of, sealed)
    return pl.concat([h, live_window]).unique(subset=["date"], keep="last").sort("date")


def overlap_hash(frame: pl.DataFrame) -> str:
    raw = frame.sort("date").write_csv().encode()
    return hashlib.sha256(raw).hexdigest()


__all__ = [
    "apply_settled_close",
    "canonical_date",
    "merge_history_live",
    "overlap_hash",
]
