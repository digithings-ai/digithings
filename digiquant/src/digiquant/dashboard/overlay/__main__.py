"""CLI: ``python -m digiquant.dashboard.overlay``."""

from __future__ import annotations

from digiquant.dashboard.overlay.cron import main

if __name__ == "__main__":
    raise SystemExit(main())
