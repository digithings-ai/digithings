"""Bulk ingest worker entrypoint (Phase 2: separate from low-latency query API).

Run: ``digisearch-worker`` or ``python -m digisearch.ingest_worker``.

Today this process logs and exits; operators can extend with a queue consumer without
changing the HTTP ``POST /ingest`` path. See digisearch/ARCHITECTURE.md (ingest vs query).
"""

from __future__ import annotations

import logging
import sys

logger = logging.getLogger(__name__)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    logger.info(
        "DigiSearch ingest worker placeholder — no queue loop yet. Use POST /ingest for synchronous ingest "
        "or extend this module with your job backend."
    )
    sys.exit(0)


if __name__ == "__main__":
    main()
