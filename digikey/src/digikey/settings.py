"""Environment-driven settings."""

from __future__ import annotations

import os

KEY_PREFIX_LEN = 16
RAW_KEY_PREFIX = "dgk_live_"


def allow_dev_global_keys() -> bool:
    return os.environ.get("DIGIKEY_ALLOW_DEV_GLOBAL", "0").strip().lower() in ("1", "true", "yes")


def admin_token() -> str:
    return (os.environ.get("DIGIKEY_ADMIN_TOKEN") or "").strip()


def bff_token() -> str:
    return (os.environ.get("DIGIKEY_BFF_TOKEN") or "").strip()
