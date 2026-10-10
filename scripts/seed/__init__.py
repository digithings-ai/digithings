"""Synthetic seed data for the self-host reference stack (DIG-2774, plan section 5).

Every value produced by this package is synthetic. No client data is read,
copied or derived, and no write ever leaves the local machine: the target
guards in :mod:`scripts.seed.deterministic` refuse any host that is not
loopback.

Deterministic by construction: same ``--seed`` produces byte-identical
output. Idempotent by construction: every write is an upsert or a
content-addressed put keyed by a natural key, so re-running converges
instead of accumulating rows.
"""
