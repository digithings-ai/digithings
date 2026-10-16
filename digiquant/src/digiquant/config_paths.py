"""Production config directory for the digiquant engine (repo-split 1b).

Canonical variable: ``DIGIQUANT_CONFIG_DIR``. Legacy alias: ``DIGI_CONFIG_PATH``
(kept working so existing deploys and tests do not break).

Resolution order for any engine config file ``<name>``:

1. ``$DIGIQUANT_CONFIG_DIR/<name>`` when the canonical var is set and non-blank.
2. ``$DIGI_CONFIG_PATH/<name>`` when only the legacy var is set and non-blank.
3. The caller-supplied bundled default (packaged neutral files shipped with the
   wheel — ``digiquant.research`` ``config/**`` package-data).

An explicitly-set directory is authoritative: when either var names a directory,
no silent fallback to the bundle happens — a wrong setting must fail loudly at
the loader, never quietly read the wrong file.
"""

from __future__ import annotations

import os
from pathlib import Path

CONFIG_DIR_ENV = "DIGIQUANT_CONFIG_DIR"
LEGACY_CONFIG_DIR_ENV = "DIGI_CONFIG_PATH"


def config_dir() -> Path | None:
    """Configured production config directory, or ``None`` when unset.

    Canonical ``DIGIQUANT_CONFIG_DIR`` wins over legacy ``DIGI_CONFIG_PATH``.
    Blank values count as unset.
    """
    primary = (os.environ.get(CONFIG_DIR_ENV) or "").strip()
    if primary:
        return Path(primary)
    legacy = (os.environ.get(LEGACY_CONFIG_DIR_ENV) or "").strip()
    if legacy:
        return Path(legacy)
    return None


def resolve_config_file(filename: str, bundled: Path) -> Path:
    """Resolve ``filename`` against the configured dir, else the bundled default."""
    configured = config_dir()
    if configured is not None:
        return configured / filename
    return bundled


__all__ = [
    "CONFIG_DIR_ENV",
    "LEGACY_CONFIG_DIR_ENV",
    "config_dir",
    "resolve_config_file",
]
