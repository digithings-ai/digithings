"""Tests for the TEMPORARY read-only licence census route (DIG-2203).

Delete this file together with ``admin_license_census`` in
``digikey/src/digikey/server.py`` once the one-time production read is done.

The route's SQL is Postgres-only (``count(*) FILTER (...)``,
``extract(epoch FROM now())::bigint``) so it cannot execute against the SQLite
database the other digikey tests use. These tests therefore split into two
groups: the auth gate runs against the real app, and the SQL surface plus the
response shaping run against a fake session.
"""

from __future__ import annotations

import re
from datetime import datetime, timezone

import pytest
from fastapi.testclient import TestClient

fakeredis = pytest.importorskip("fakeredis")

ADMIN_HEADERS = {"Authorization": "Bearer admin-secret"}

# The two statements approved in DIG-2203, verbatim. Whitespace is normalised
# before comparison because the constants are concatenated across lines.
APPROVED_TOTALS_SQL = """
SELECT
  count(*)                                          AS total_rows,
  count(*) FILTER (WHERE revoked_at IS NOT NULL)    AS revoked_rows,
  count(*) FILTER (WHERE expires_at  <  extract(epoch FROM now())::bigint)
                                                    AS expired_rows,
  min(issued_at)                                    AS oldest_issued_at,
  max(issued_at)                                    AS newest_issued_at
FROM digikey_licenses;
"""

APPROVED_BY_CUSTOMER_SQL = """
SELECT customer_slug, count(*) AS licences
FROM digikey_licenses
GROUP BY customer_slug
ORDER BY customer_slug;
"""


def _norm(sql: str) -> str:
    """Collapse whitespace and strip the trailing statement semicolon."""
    return re.sub(r"\s+", " ", sql).strip().rstrip(";").strip()


@pytest.fixture()
def client(monkeypatch, tmp_path):
    db_path = tmp_path / "dk.db"
    monkeypatch.setenv("DIGIKEY_DATABASE_URL", f"sqlite:///{db_path}")
    monkeypatch.setenv("DIGIKEY_ALLOW_EPHEMERAL_KEY", "1")
    monkeypatch.setenv("DIGIKEY_ADMIN_TOKEN", "admin-secret")
    monkeypatch.setenv("DIGIKEY_BLOCKLIST_REDIS_URL", "redis://fake")
    from digikey import blocklist, db

    db._engine = None
    db._session_factory = None
    blocklist.reset_client_cache()

    fake = fakeredis.FakeRedis(decode_responses=True)
    monkeypatch.setattr(blocklist, "_get_client", lambda: fake)

    from digikey.server import app

    with TestClient(app) as c:
        yield c


class _FakeResult:
    def __init__(self, rows):
        self._rows = list(rows)

    def mappings(self):
        return self

    def one(self):
        return self._rows[0]

    def all(self):
        return list(self._rows)


class _FakeSession:
    """Records every ``execute`` call so tests can assert on the SQL surface."""

    def __init__(self, results):
        self._results = list(results)
        self.executed: list[tuple[str, object]] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def execute(self, statement, params=None):
        self.executed.append((str(statement), params))
        if not self._results:
            raise AssertionError("route executed more statements than the two approved ones")
        return self._results.pop(0)

    def commit(self):
        raise AssertionError("the census route must never commit")


def _patch_session(monkeypatch, results):
    session = _FakeSession(results)
    # The route does ``sf = session_factory(); with sf() as session:`` so the
    # patched name must return a callable that yields the fake session.
    monkeypatch.setattr("digikey.server.session_factory", lambda: lambda: session)
    return session


def _totals_row(**over):
    row = {
        "total_rows": 7,
        "revoked_rows": 2,
        "expired_rows": 3,
        "oldest_issued_at": datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc),
        "newest_issued_at": datetime(2026, 5, 6, 7, 8, 9, tzinfo=timezone.utc),
    }
    row.update(over)
    return row


# --- auth gate (real app, no SQL needed) -----------------------------------


@pytest.mark.unit
def test_census_requires_admin_token(client: TestClient):
    assert client.get("/v1/admin/licenses/census").status_code == 401


@pytest.mark.unit
def test_census_rejects_wrong_token(client: TestClient):
    r = client.get(
        "/v1/admin/licenses/census",
        headers={"Authorization": "Bearer not-the-token"},
    )
    assert r.status_code == 401


@pytest.mark.unit
def test_census_route_is_registered(client: TestClient):
    assert "/v1/admin/licenses/census" in {
        route.path for route in client.app.routes if hasattr(route, "path")
    }


# --- the SQL surface is exactly what DIG-2203 approved ----------------------


def test_census_sql_matches_approved_statements():
    from digikey.server import _LICENSE_CENSUS_BY_CUSTOMER_SQL, _LICENSE_CENSUS_TOTALS_SQL

    assert _norm(str(_LICENSE_CENSUS_TOTALS_SQL)) == _norm(APPROVED_TOTALS_SQL)
    assert _norm(str(_LICENSE_CENSUS_BY_CUSTOMER_SQL)) == _norm(APPROVED_BY_CUSTOMER_SQL)


@pytest.mark.parametrize(
    "constant",
    ["_LICENSE_CENSUS_TOTALS_SQL", "_LICENSE_CENSUS_BY_CUSTOMER_SQL"],
)
def test_census_sql_has_no_bound_parameters(constant):
    """No ``:name`` placeholders => no caller input can reach the SQL text."""
    from digikey import server

    sql = str(getattr(server, constant))
    assert re.search(r"(?<![:\w]):[A-Za-z_]\w*", sql) is None


@pytest.mark.parametrize(
    "constant",
    ["_LICENSE_CENSUS_TOTALS_SQL", "_LICENSE_CENSUS_BY_CUSTOMER_SQL"],
)
def test_census_sql_contains_no_writes(constant):
    from digikey import server

    sql = _norm(str(getattr(server, constant))).upper()
    for keyword in ("INSERT", "UPDATE", "DELETE", "TRUNCATE", "DROP", "ALTER", "GRANT"):
        assert keyword not in sql


@pytest.mark.parametrize(
    "constant",
    ["_LICENSE_CENSUS_TOTALS_SQL", "_LICENSE_CENSUS_BY_CUSTOMER_SQL"],
)
def test_census_sql_touches_only_the_licenses_table(constant):
    from digikey import server

    sql = _norm(str(getattr(server, constant)))
    # ``extract(epoch FROM now())`` contains a FROM that is not a table
    # reference; drop that fragment before collecting table names.
    sql = sql.replace("extract(epoch FROM now())", "")
    assert re.findall(r"\b(?:FROM|JOIN)\s+([A-Za-z_]\w*)", sql) == ["digikey_licenses"]


def test_census_expired_rows_uses_integer_epoch_not_timestamp():
    """``expires_at`` is an integer unix exp, so a timestamp compare would be wrong."""
    from digikey.server import _LICENSE_CENSUS_TOTALS_SQL

    sql = _norm(str(_LICENSE_CENSUS_TOTALS_SQL))
    assert "extract(epoch FROM now())::bigint" in sql
    assert "expires_at < now()" not in sql


# --- response shaping (fake session) ---------------------------------------


@pytest.mark.unit
def test_census_returns_only_the_approved_fields(client: TestClient, monkeypatch):
    _patch_session(
        monkeypatch,
        [
            _FakeResult([_totals_row()]),
            _FakeResult(
                [
                    {"customer_slug": "acme", "licences": 5},
                    {"customer_slug": "globex", "licences": 2},
                ]
            ),
        ],
    )
    r = client.get("/v1/admin/licenses/census", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert set(body) == {
        "total_rows",
        "revoked_rows",
        "expired_rows",
        "oldest_issued_at",
        "newest_issued_at",
        "per_customer",
    }
    assert body["total_rows"] == 7
    assert body["revoked_rows"] == 2
    assert body["expired_rows"] == 3
    assert body["oldest_issued_at"].startswith("2026-01-02")
    assert body["newest_issued_at"].startswith("2026-05-06")
    assert body["per_customer"] == [
        {"customer_slug": "acme", "licences": 5},
        {"customer_slug": "globex", "licences": 2},
    ]


@pytest.mark.unit
def test_census_empty_table_returns_null_timestamps(client: TestClient, monkeypatch):
    _patch_session(
        monkeypatch,
        [
            _FakeResult([_totals_row(total_rows=0, oldest_issued_at=None, newest_issued_at=None)]),
            _FakeResult([]),
        ],
    )
    r = client.get("/v1/admin/licenses/census", headers=ADMIN_HEADERS)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["oldest_issued_at"] is None
    assert body["newest_issued_at"] is None
    assert body["per_customer"] == []


@pytest.mark.unit
def test_census_leaks_no_licence_rows_or_tokens(client: TestClient, monkeypatch):
    """The payload must not carry extra keys that a caller could not have asked for."""
    _patch_session(
        monkeypatch,
        [
            _FakeResult([_totals_row()]),
            _FakeResult([{"customer_slug": "acme", "licences": 7, "license_id": "leak"}]),
        ],
    )
    body = client.get("/v1/admin/licenses/census", headers=ADMIN_HEADERS).json()
    assert body["per_customer"] == [{"customer_slug": "acme", "licences": 7}]


@pytest.mark.unit
def test_census_runs_exactly_the_two_approved_statements(client: TestClient, monkeypatch):
    session = _patch_session(
        monkeypatch,
        [_FakeResult([_totals_row()]), _FakeResult([{"customer_slug": "acme", "licences": 1}])],
    )
    assert client.get("/v1/admin/licenses/census", headers=ADMIN_HEADERS).status_code == 200
    assert [_norm(sql) for sql, _ in session.executed] == [
        _norm(APPROVED_TOTALS_SQL),
        _norm(APPROVED_BY_CUSTOMER_SQL),
    ]
    assert all(params is None for _, params in session.executed)


@pytest.mark.unit
def test_census_query_and_body_never_reach_sql(client: TestClient, monkeypatch):
    session = _patch_session(
        monkeypatch,
        [_FakeResult([_totals_row()]), _FakeResult([{"customer_slug": "acme", "licences": 1}])],
    )
    r = client.get(
        "/v1/admin/licenses/census",
        headers=ADMIN_HEADERS,
        params={"customer_slug": "'; DROP TABLE digikey_licenses; --", "extra": "x"},
    )
    assert r.status_code == 200, r.text
    assert [_norm(sql) for sql, _ in session.executed] == [
        _norm(APPROVED_TOTALS_SQL),
        _norm(APPROVED_BY_CUSTOMER_SQL),
    ]
    assert all(params is None for _, params in session.executed)


@pytest.mark.unit
def test_census_store_failure_returns_503_without_leaking_the_dsn(
    client: TestClient, monkeypatch, caplog
):
    secret = "postgresql://user:password@host.example/digikey"

    class _Boom(_FakeSession):
        def execute(self, statement, params=None):
            raise RuntimeError(f"connection to {secret} failed")

    monkeypatch.setattr("digikey.server.session_factory", lambda: lambda: _Boom([]))
    r = client.get("/v1/admin/licenses/census", headers=ADMIN_HEADERS)
    assert r.status_code == 503
    # digibase wraps HTTPException detail into its standard error envelope.
    assert "license_store_unavailable" in r.text
    assert secret not in r.text
    assert secret not in caplog.text
