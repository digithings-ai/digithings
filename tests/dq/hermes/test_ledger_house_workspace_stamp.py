"""House ``workspace_id`` stamp on main H9 writers (097 NOT NULL, no tenancy import)."""

from __future__ import annotations

from uuid import UUID

import pytest
from digiquant.olympus.atlas.supabase_io import HOUSE_WORKSPACE_ID
from digiquant.olympus.hermes.models.portfolio_ledger import PortfolioCommit
from digiquant.olympus.hermes.writers.ledger_io import COMMITS, _insert

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient

pytestmark = pytest.mark.unit

_HOUSE = "6b753576-ced9-5319-9bfa-c5d0aacd9319"


def test_house_workspace_id_matches_documents_constant() -> None:
    assert HOUSE_WORKSPACE_ID == _HOUSE
    assert isinstance(HOUSE_WORKSPACE_ID, str)


def test_insert_stamps_house_workspace_as_string() -> None:
    client = FakeSupabaseClient()
    _insert(client=client, table=COMMITS, rows=[{"id": "c1", "run_date": "2026-08-31"}])
    rows = client.store[COMMITS]
    assert len(rows) == 1
    assert rows[0]["workspace_id"] == _HOUSE
    assert isinstance(rows[0]["workspace_id"], str)
    assert "_on_conflict" not in rows[0]


def test_insert_stringifies_uuid_workspace_id() -> None:
    client = FakeSupabaseClient()
    overlay = UUID("aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee")
    _insert(client=client, table=COMMITS, rows=[{"id": "c1", "workspace_id": overlay}])
    assert client.store[COMMITS][0]["workspace_id"] == str(overlay)


def test_insert_empty_rows_is_noop() -> None:
    client = FakeSupabaseClient()
    _insert(client=client, table=COMMITS, rows=[])
    assert COMMITS not in client.store


def test_commit_model_defaults_to_house_workspace() -> None:
    parsed = PortfolioCommit.model_validate(
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "run_date": "2026-08-31",
            "policy_version_id": "policy-v1",
            "effective_at": "2026-08-31T21:00:00+00:00",
            "recorded_at": "2026-08-31T21:00:00+00:00",
        }
    )
    assert str(parsed.workspace_id) == _HOUSE


def test_stamped_commit_round_trips_model_validate() -> None:
    parsed = PortfolioCommit.model_validate(
        {
            "id": "aaaaaaaa-bbbb-cccc-dddd-eeeeeeeeeeee",
            "run_date": "2026-08-31",
            "policy_version_id": "policy-v1",
            "effective_at": "2026-08-31T21:00:00+00:00",
            "recorded_at": "2026-08-31T21:00:00+00:00",
            "workspace_id": _HOUSE,
        }
    )
    assert str(parsed.workspace_id) == _HOUSE
    assert parsed.workspace_id == UUID(_HOUSE)
