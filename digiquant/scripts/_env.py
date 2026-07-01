"""Load repo ``.env`` for DigiQuant CLI scripts (Supabase credentials, etc.)."""

from __future__ import annotations

from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]


def load_repo_env() -> None:
    """Best-effort ``.env`` load from the monorepo root."""
    try:
        from dotenv import load_dotenv
    except ImportError:  # pragma: no cover - optional in minimal installs
        return
    load_dotenv(_REPO_ROOT / ".env", override=False)
