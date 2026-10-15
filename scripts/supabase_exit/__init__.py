"""Local-only Supabase -> D1 data migration tooling (DIG-2893).

Reads a ``pg_dump --column-inserts`` dump file from local disk, splits it per
table, and replays it into a **local** SQLite database (the stand-in for local
D1; the same file imports into D1 via ``wrangler d1 execute --local``) in
explicit batches inside transactions. Verification is row counts plus a
SHA-256 checksum per table over canonically ordered rows.

Hard local-only guards (see ``_assert_local_only``):

* the dump must be a plain local file -- never a URL, never stdin-from-network;
* the target must be a local SQLite file -- this package offers no remote
  flag, no D1 REST client, no Supabase reader. Live Supabase stays untouched
  and no production cutover happens here (that needs Chris's approval on
  tickets 14/15).

No data work runs until Chris's snapshot exists (ticket 0, DIG-2888): the
script takes the snapshot dump file as its input and refuses anything else.
Schema (DDL) comes from tickets 2/3 -- this script creates no tables itself,
it only inserts into tables the target DDL already defines.
"""

from __future__ import annotations
