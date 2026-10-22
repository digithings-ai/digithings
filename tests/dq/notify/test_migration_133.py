"""The #4384 notification claim split, pinned on the grants.

DELETE on the claim table is granted; the append-only log never is.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.unit


def test_migration_133_grants_the_claim_delete_and_keeps_the_log_append_only() -> None:
    """The #4384 split, pinned: DELETE on the claim, never on the log."""
    from pathlib import Path

    root = Path(__file__).resolve().parents[3] / "digiquant" / "supabase" / "migrations"
    prod = root / "prod"
    claim = (prod / "133_notification_claim.sql").read_text()
    assert "CREATE TABLE IF NOT EXISTS public.notification_claim" in claim
    assert "GRANT SELECT, INSERT, DELETE ON public.notification_claim TO service_role" in claim
    assert "reject_notification_claim" not in claim

    canonical = (prod / "106_notification_prefs_align_canonical.sql").read_text()
    assert "GRANT SELECT, INSERT ON public.notification_log TO service_role" in canonical
    assert "reject_notification_log_mutation" in canonical
    offenders = [
        f"{path.name}: {line.strip()}"
        for path in sorted(root.rglob("*.sql"))
        for line in path.read_text().splitlines()
        if line.strip().startswith("GRANT") and "notification_log" in line and "DELETE" in line
    ]
    assert offenders == [], offenders
