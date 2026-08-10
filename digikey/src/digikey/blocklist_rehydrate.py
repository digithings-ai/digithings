"""Repopulate Redis jti blocklist from durable ``jti_issued`` rows (ADR-0007).

After Redis restarts empty, revoked keys' live JTIs must be rewritten from Postgres/SQLite.
"""

from __future__ import annotations

import logging
import time

from sqlalchemy import select

from digikey import blocklist
from digikey.db_schema import ApiKeyRow, JtiIssuedRow

logger = logging.getLogger(__name__)


def rehydrate_blocklist_from_db(session_factory) -> int:
    """Push all live JTIs for revoked API keys into Redis.

    Returns the number of entries written. No-op when blocklist Redis is unset.
    """
    if not blocklist.is_configured():
        return 0
    now_ts = int(time.time())
    sf = session_factory()
    with sf() as session:
        rows = session.execute(
            select(JtiIssuedRow.jti, JtiIssuedRow.exp)
            .join(ApiKeyRow, JtiIssuedRow.api_key_id == ApiKeyRow.id)
            .where(
                ApiKeyRow.revoked_at.is_not(None),
                JtiIssuedRow.exp > now_ts,
            )
        ).all()
    entries = [(str(jti), int(exp) - now_ts) for jti, exp in rows]
    if not entries:
        return 0
    written = blocklist.write_blocklist_bulk(entries)
    logger.info("blocklist rehydrate: wrote %s jti entries from %s revoked-key rows", written, len(entries))
    return written
