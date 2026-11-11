"""The digivault MCP surface binds ``path_prefix`` to the caller's verified tenant (#6648).

Before this, every MCP tool took ``path_prefix`` straight from its arguments, so
any holder of a digikey JWT that opened the edge could read (and, with the write
scope, create) notes under another tenant's prefix. The HTTP API already
enforced the binding (``server.py`` ``enforce_tenant_path_prefix``).

Pinned here:

- tenant A with tenant B's prefix is refused on every tool, before the vault or
  any store is opened;
- a blank prefix resolves to the token tenant's own prefix, never the vault;
- a claimless, unverifiable or wrong-scope bearer is refused (fail closed);
- the house chat path (bearer tenant = house, setup prefix = house prefix) works;
- no ``Authorization`` header (static edge key / in-network) is unchanged.

Offline: tokens are minted with the pytest keypair from ``tests/conftest.py``.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

import pytest
from digivault.mcp_tenant import McpTenantRefused, resolve_mcp_path_prefix
from digivault.tool_dispatch import (
    MCP_TOOL_BACKLINKS,
    MCP_TOOL_CREATE_NOTE,
    MCP_TOOL_LINT,
    MCP_TOOL_SEARCH_NOTES,
    MCP_TOOL_SEARCH_TAG,
    register_mcp_tools,
)
from digivault.vault import Vault

from digivault import mcp_tenant
from tests.digi_test_jwt import mint_test_jwt

pytestmark = pytest.mark.unit

HOUSE = "digithings-ai"
TENANT_A = "tenant-a"
TENANT_B = "tenant-b"
HOUSE_PREFIX = "clients/digithings"
A_PREFIX = "clients/tenant-a"
B_PREFIX = "clients/tenant-b"

CORPUS_MAP = json.dumps(
    {
        "digithings": {"digisearchIndex": "digithings_docs", "vaultPathPrefix": HOUSE_PREFIX},
        HOUSE: {"digisearchIndex": "digithings_docs", "vaultPathPrefix": HOUSE_PREFIX},
        TENANT_A: {"digisearchIndex": "tenant_a_help", "vaultPathPrefix": A_PREFIX},
        TENANT_B: {"digisearchIndex": "tenant_b_help", "vaultPathPrefix": B_PREFIX},
    }
)


def _bearer(tenant: str, scopes: list[str] | None = None) -> str:
    return f"Bearer {mint_test_jwt(tenant_slug=tenant, scopes=scopes or ['mcp:digivault'])}"


def _vault(tmp_path: Path) -> Vault:
    for prefix, title in ((HOUSE_PREFIX, "House"), (A_PREFIX, "Alpha"), (B_PREFIX, "Bravo")):
        d = tmp_path / prefix
        d.mkdir(parents=True)
        stem = title.lower()
        (d / f"{stem}-hub.md").write_text(
            f"---\ntitle: {title} hub\ntags: [guide]\n---\nsee [[{stem}-doc]]\n", encoding="utf-8"
        )
        (d / f"{stem}-doc.md").write_text(
            f"---\ntitle: {title} doc\ntags: [guide]\n---\nsee [[{stem}-hub]]\n", encoding="utf-8"
        )
    return Vault(tmp_path)


class _FakeMcp:
    """FastMCP stand-in whose request context carries ``authorization``."""

    def __init__(self) -> None:
        self.tools: dict[str, object] = {}
        self.authorization: str | None = None

    def tool(self, *, name: str):
        def deco(fn):
            self.tools[name] = fn
            return fn

        return deco

    def get_context(self):
        headers = {} if self.authorization is None else {"authorization": self.authorization}
        return SimpleNamespace(
            request_context=SimpleNamespace(request=SimpleNamespace(headers=headers))
        )


@pytest.fixture
def corpus_map(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", CORPUS_MAP)


@pytest.fixture
def surface(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> _FakeMcp:
    monkeypatch.setenv("DIGIVAULT_MCP_WRITE", "1")
    fake = _FakeMcp()
    vault = _vault(tmp_path)
    register_mcp_tools(fake, lambda: vault)
    return fake


def _call(fake: _FakeMcp, tool: str, *args, **kwargs) -> str:
    return fake.tools[tool](*args, **kwargs)  # type: ignore[operator]


def _tag_names(raw: str) -> set[str]:
    return {row["name"] for row in json.loads(raw)}


# ── resolve_mcp_path_prefix ──────────────────────────────────────────────────


def _verify_as(tenant: str | None):
    return lambda _header: tenant


def test_no_authorization_keeps_the_requested_prefix() -> None:
    assert resolve_mcp_path_prefix(None, B_PREFIX, raw_map=CORPUS_MAP) == B_PREFIX
    assert resolve_mcp_path_prefix("", None, raw_map=CORPUS_MAP) is None


def test_other_tenants_prefix_is_refused() -> None:
    with pytest.raises(McpTenantRefused, match="not available to this caller"):
        resolve_mcp_path_prefix(
            "Bearer x", B_PREFIX, verify=_verify_as(TENANT_A), raw_map=CORPUS_MAP
        )


@pytest.mark.parametrize("blank", [None, "", "   "])
def test_blank_prefix_resolves_to_the_token_tenant(blank: str | None) -> None:
    got = resolve_mcp_path_prefix(
        "Bearer x", blank, verify=_verify_as(TENANT_A), raw_map=CORPUS_MAP
    )
    assert got == A_PREFIX


def test_own_prefix_is_allowed_in_any_spelling() -> None:
    for spelling in (A_PREFIX, f"{A_PREFIX}/", f"/{A_PREFIX}"):
        got = resolve_mcp_path_prefix(
            "Bearer x", spelling, verify=_verify_as(TENANT_A), raw_map=CORPUS_MAP
        )
        assert got == A_PREFIX


def test_unverified_or_claimless_bearer_is_refused() -> None:
    with pytest.raises(McpTenantRefused, match="no verified tenant"):
        resolve_mcp_path_prefix("Bearer x", A_PREFIX, verify=_verify_as(None), raw_map=CORPUS_MAP)


def test_non_bearer_authorization_is_refused() -> None:
    with pytest.raises(McpTenantRefused, match="unsupported authorization"):
        resolve_mcp_path_prefix(
            "Basic abc", A_PREFIX, verify=_verify_as(TENANT_A), raw_map=CORPUS_MAP
        )


def test_tenant_absent_from_the_map_is_refused() -> None:
    with pytest.raises(McpTenantRefused, match="not available to this caller"):
        resolve_mcp_path_prefix("Bearer x", None, verify=_verify_as("stranger"), raw_map=CORPUS_MAP)


def test_broken_map_fails_closed() -> None:
    with pytest.raises(McpTenantRefused, match="misconfigured"):
        resolve_mcp_path_prefix("Bearer x", A_PREFIX, verify=_verify_as(TENANT_A), raw_map="{nope")


def test_single_tenant_deployment_keeps_the_requested_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)
    got = resolve_mcp_path_prefix("Bearer x", "notes", verify=_verify_as(TENANT_A))
    assert got == "notes"


# ── verified_tenant_from_bearer (real signature check, pytest keypair) ────────


def test_bearer_with_the_mcp_scope_yields_its_tenant() -> None:
    assert mcp_tenant.verified_tenant_from_bearer(_bearer(TENANT_A)) == TENANT_A
    assert mcp_tenant.verified_tenant_from_bearer(_bearer(TENANT_A, ["mcp:*"])) == TENANT_A


def test_bearer_without_the_mcp_scope_has_no_tenant() -> None:
    assert mcp_tenant.verified_tenant_from_bearer(_bearer(TENANT_A, ["digisearch:query"])) is None


def test_claimless_bearer_has_no_tenant() -> None:
    assert mcp_tenant.verified_tenant_from_bearer(_bearer("")) is None


def test_garbage_bearer_has_no_tenant() -> None:
    assert mcp_tenant.verified_tenant_from_bearer("Bearer not.a.jwt") is None
    assert mcp_tenant.verified_tenant_from_bearer("Bearer ") is None


def test_revoked_bearer_has_no_tenant(monkeypatch: pytest.MonkeyPatch) -> None:
    from digikey import blocklist

    monkeypatch.setattr(blocklist, "is_configured", lambda: True)
    monkeypatch.setattr(blocklist, "is_blocked", lambda jti: True)
    assert mcp_tenant.verified_tenant_from_bearer(_bearer(TENANT_A)) is None


# ── the MCP tools themselves ─────────────────────────────────────────────────


@pytest.mark.usefixtures("corpus_map")
def test_tenant_a_cannot_search_tenant_b(surface: _FakeMcp) -> None:
    surface.authorization = _bearer(TENANT_A)
    raw = _call(surface, MCP_TOOL_SEARCH_TAG, "guide", path_prefix=B_PREFIX)
    assert raw.startswith("[digivault error:")
    assert "bravo" not in raw


@pytest.mark.usefixtures("corpus_map")
def test_tenant_a_cannot_read_tenant_b_backlinks_or_lint(surface: _FakeMcp) -> None:
    surface.authorization = _bearer(TENANT_A)
    raw = _call(surface, MCP_TOOL_BACKLINKS, "bravo-hub", path_prefix=B_PREFIX)
    assert raw.startswith("[digivault error:") and "bravo-doc" not in raw
    raw = _call(surface, MCP_TOOL_LINT, path_prefix=B_PREFIX)
    assert raw.startswith("[digivault error:")


@pytest.mark.usefixtures("corpus_map")
def test_tenant_a_cannot_create_in_tenant_b(surface: _FakeMcp, tmp_path: Path) -> None:
    surface.authorization = _bearer(TENANT_A, ["mcp:digivault", "mcp:digivault:write"])
    raw = _call(surface, MCP_TOOL_CREATE_NOTE, "planted", body="x", path_prefix=B_PREFIX)
    assert raw.startswith("[digivault error:")
    assert not (tmp_path / B_PREFIX / "planted.md").exists()


@pytest.mark.usefixtures("corpus_map")
def test_tenant_a_cannot_full_text_search_tenant_b(
    surface: _FakeMcp, monkeypatch: pytest.MonkeyPatch
) -> None:
    """``search_notes`` is refused before any D1/local/Supabase store is opened."""
    import digivault.server as server

    def boom(*_a, **_k):
        raise AssertionError("a refused call must not open a store")

    monkeypatch.setattr(server, "_open_d1_store", boom)
    monkeypatch.setattr(server, "_open_supabase_store", boom)
    surface.authorization = _bearer(TENANT_A)
    raw = _call(surface, MCP_TOOL_SEARCH_NOTES, "hub", path_prefix=B_PREFIX)
    assert raw == "[digivault error: path_prefix is not available to this caller]"


@pytest.mark.usefixtures("corpus_map")
def test_blank_prefix_reads_only_the_token_tenant(surface: _FakeMcp) -> None:
    surface.authorization = _bearer(TENANT_A)
    for blank in (None, "", "  "):
        raw = _call(surface, MCP_TOOL_SEARCH_TAG, "guide", path_prefix=blank)
        assert _tag_names(raw) == {"alpha-hub", "alpha-doc"}


@pytest.mark.usefixtures("corpus_map")
def test_blank_prefix_create_lands_in_the_token_tenant(surface: _FakeMcp, tmp_path: Path) -> None:
    surface.authorization = _bearer(TENANT_A, ["mcp:digivault", "mcp:digivault:write"])
    created = json.loads(_call(surface, MCP_TOOL_CREATE_NOTE, "fresh", body="x"))
    assert created["rel_path"] == f"{A_PREFIX}/fresh.md"
    assert not (tmp_path / "fresh.md").exists()


@pytest.mark.usefixtures("corpus_map")
def test_claimless_bearer_is_refused_on_every_tool(surface: _FakeMcp) -> None:
    surface.authorization = _bearer("")
    for tool, args in (
        (MCP_TOOL_SEARCH_TAG, ("guide",)),
        (MCP_TOOL_BACKLINKS, ("alpha-hub",)),
        (MCP_TOOL_LINT, ()),
        (MCP_TOOL_CREATE_NOTE, ("x",)),
        (MCP_TOOL_SEARCH_NOTES, ("hub",)),
    ):
        raw = _call(surface, tool, *args, path_prefix=A_PREFIX)
        assert raw == "[digivault error: caller has no verified tenant]", tool


@pytest.mark.usefixtures("corpus_map")
def test_bearer_without_the_vault_scope_is_refused(surface: _FakeMcp) -> None:
    surface.authorization = _bearer(TENANT_A, ["mcp:digisearch"])
    raw = _call(surface, MCP_TOOL_SEARCH_TAG, "guide", path_prefix=A_PREFIX)
    assert raw == "[digivault error: caller has no verified tenant]"


@pytest.mark.usefixtures("corpus_map")
def test_house_chat_path_still_works(surface: _FakeMcp) -> None:
    """digigraph merges ``setup.path_prefix`` (the house prefix) over the model's
    arguments and sends the BFF token minted for the house tenant."""
    surface.authorization = _bearer(HOUSE, ["mcp:digisearch", "mcp:digivault"])
    raw = _call(surface, MCP_TOOL_SEARCH_TAG, "guide", path_prefix=HOUSE_PREFIX)
    assert _tag_names(raw) == {"house-hub", "house-doc"}
    payload = json.loads(_call(surface, MCP_TOOL_BACKLINKS, "house-hub", path_prefix=HOUSE_PREFIX))
    assert payload["backlinks"] == ["house-doc"]


@pytest.mark.usefixtures("corpus_map")
def test_no_authorization_header_is_unchanged(surface: _FakeMcp) -> None:
    """The static edge key / in-network compat path carries no bearer."""
    surface.authorization = None
    raw = _call(surface, MCP_TOOL_SEARCH_TAG, "guide", path_prefix=B_PREFIX)
    assert _tag_names(raw) == {"bravo-hub", "bravo-doc"}


def test_mcp_reads_the_bearer_from_the_real_http_request(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """End to end over streamable HTTP: the tools see the request's own header."""
    pytest.importorskip("mcp.server.fastmcp")
    from fastapi.testclient import TestClient
    from mcp.server.fastmcp import FastMCP

    monkeypatch.setenv("DIGI_TENANT_CORPUS_MAP", CORPUS_MAP)
    vault = _vault(tmp_path)
    probe = FastMCP("digivault-scope-probe", json_response=True, stateless_http=True)
    register_mcp_tools(probe, lambda: vault)

    def call(c: TestClient, header: str | None, prefix: str) -> str:
        frame = {
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {
                "name": MCP_TOOL_SEARCH_TAG,
                "arguments": {"tag": "guide", "path_prefix": prefix},
            },
        }
        headers = {
            "accept": "application/json, text/event-stream",
            "content-type": "application/json",
        }
        if header:
            headers["authorization"] = header
        r = c.post("/mcp", json=frame, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["result"]["content"][0]["text"]

    app = probe.streamable_http_app()
    with TestClient(app, base_url="http://127.0.0.1:8769") as c:
        refused = call(c, _bearer(TENANT_A), B_PREFIX)
        assert refused == "[digivault error: path_prefix is not available to this caller]"
        own = call(c, _bearer(TENANT_A), "")
        assert _tag_names(own) == {"alpha-hub", "alpha-doc"}
        claimless = call(c, _bearer(""), A_PREFIX)
        assert claimless == "[digivault error: caller has no verified tenant]"
