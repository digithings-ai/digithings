"""DIG-4488: the digichat tenant registry is composed, never applied from a repo file."""

import importlib.util
import json
import os
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO = Path(__file__).resolve().parents[2]
SCRIPT = REPO / "scripts" / "digichat_tenant_registry.py"
STAGED = REPO / "infra" / "digichat-release" / "DIG-3556-staged-prod-tenant-config.json"


def _load_module():
    spec = importlib.util.spec_from_file_location("digichat_tenant_registry", str(SCRIPT))
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


registry = _load_module()


# A fake live registry. The token values are test strings, not secrets.
LIVE = {
    "digithings.ai": {
        "slug": "digithings",
        "gateMode": "ungated",
        "attribution": False,
        "webSearch": True,
        "token": "tok-first-party",
        "backend": {"type": "digigraph"},
    },
    "occ.digithings.ai": {
        "slug": "occ",
        "gateMode": "ungated",
        "attribution": False,
        "webSearch": False,
        "token": "tok-occ",
        "backend": {
            "type": "digigraph",
            # Synthetic corpus routing. The real corpus name is a client
            # literal and lives in the private release-lane paths, so this
            # fixture never writes it down.
            "digisearchIndex": "tenant_corpus",
            "vaultPathPrefix": "clients/tenant-vault",
        },
    },
    "digiquant.io": {
        "slug": "digiquant",
        "gateMode": "ungated",
        "webSearch": True,
        "token": "tok-digiquant",
        "backend": {"type": "digigraph"},
    },
}


def _staged_overlay():
    with STAGED.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def test_compose_keeps_every_live_tenant_and_token():
    overlay = {"digithings.ai": {"backend": {"digisearchIndex": "digithings_docs"}}}
    composed, report = registry.compose_registry(LIVE, overlay)
    assert sorted(composed) == sorted(LIVE)
    for host, entry in LIVE.items():
        assert composed[host]["token"] == entry["token"]
    assert composed["digithings.ai"]["backend"]["digisearchIndex"] == "digithings_docs"
    assert "digithings.ai.backend.digisearchIndex" in report["changed_paths"]


def test_compose_keeps_live_backend_keys_the_overlay_omits():
    composed, _ = registry.compose_registry(
        LIVE, {"occ.digithings.ai": {"backend": {"type": "digigraph"}}}
    )
    live_backend = LIVE["occ.digithings.ai"]["backend"]
    assert (
        composed["occ.digithings.ai"]["backend"]["digisearchIndex"]
        == live_backend["digisearchIndex"]
    )
    assert (
        composed["occ.digithings.ai"]["backend"]["vaultPathPrefix"]
        == live_backend["vaultPathPrefix"]
    )


def test_the_repo_file_cannot_be_used_as_the_registry():
    """The DIG-4488 failure: a repository file written as the registry."""
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(_staged_overlay(), {})
    assert "no token" in str(refusal.value)


def test_the_repo_overlay_composes_onto_the_live_registry():
    document = _staged_overlay()
    overlay = registry.load_registry(document, str(STAGED))
    composed, _ = registry.compose_registry(LIVE, overlay)
    assert sorted(composed) == sorted(LIVE)
    assert composed["occ.digithings.ai"]["token"] == LIVE["occ.digithings.ai"]["token"]
    assert (
        composed["occ.digithings.ai"]["backend"]["digisearchIndex"]
        == LIVE["occ.digithings.ai"]["backend"]["digisearchIndex"]
    )


def test_the_repo_overlay_carries_the_occ_tenant():
    overlay = registry.load_registry(_staged_overlay(), str(STAGED))
    assert "occ.digithings.ai" in overlay
    assert "token" not in overlay["occ.digithings.ai"]
    assert "mcp" not in overlay["occ.digithings.ai"]


def test_overlay_with_a_token_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"digithings.ai": {"token": "from-the-repo"}})
    assert "token" in str(refusal.value)


def test_overlay_with_mcp_rows_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"occ.digithings.ai": {"mcp": {"servers": []}}})
    assert "mcp" in str(refusal.value)


def test_overlay_that_adds_a_tenant_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"new.digithings.ai": {"slug": "new"}})
    assert "does not have" in str(refusal.value)


def test_overlay_with_an_unknown_key_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"digithings.ai": {"notAKey": 1}})
    assert "unknown key" in str(refusal.value)


def test_overlay_with_an_unknown_nested_key_is_refused():
    """The staged file carried gate.webSearch; the runtime reads gate.consumeUrl."""
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"digithings.ai": {"gate": {"webSearch": False}}})
    assert "gate.webSearch is not a key the runtime reads" in str(refusal.value)


def test_overlay_with_an_unknown_backend_key_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"digithings.ai": {"backend": {"indexName": "x"}}})
    assert "backend.indexName is not a key the runtime reads" in str(refusal.value)


def test_the_retired_occ_corpus_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(
            LIVE, {"occ.digithings.ai": {"backend": {"digisearchIndex": "occ_tickets"}}}
        )
    assert "occ_tickets" in str(refusal.value)


def test_the_overlay_may_not_set_the_occ_tenant_corpus():
    """The overlay may not repoint a client tenant's corpus routing."""
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(
            LIVE, {"occ.digithings.ai": {"backend": {"digisearchIndex": "other_index"}}}
        )
    assert "may not set digisearchIndex" in str(refusal.value)


def test_the_overlay_may_not_set_the_occ_tenant_vault_path():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(
            LIVE, {"occ.digithings.ai": {"backend": {"vaultPathPrefix": "clients/other"}}}
        )
    assert "may not set vaultPathPrefix" in str(refusal.value)


def test_a_live_registry_without_a_corpus_for_the_occ_tenant_is_refused():
    """The composed registry must never drop the OCC corpus."""
    broken = json.loads(json.dumps(LIVE))
    del broken["occ.digithings.ai"]["backend"]["digisearchIndex"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(broken, {})
    assert "does not route" in str(refusal.value)


def test_a_live_registry_without_a_token_is_refused():
    broken = json.loads(json.dumps(LIVE))
    del broken["digithings.ai"]["token"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(broken, {})
    assert "no token" in str(refusal.value)


def test_the_plan_never_prints_a_token_value():
    composed, report = registry.compose_registry(
        LIVE, {"digithings.ai": {"backend": {"digisearchIndex": "digithings_docs"}}}
    )
    plan = registry.render_plan(composed, report, "live", "overlay")
    for entry in LIVE.values():
        assert entry["token"] not in plan
    assert "digithings.ai.backend.digisearchIndex" in plan


def test_the_composed_registry_cannot_be_written_inside_the_repository(tmp_path):
    composed, _ = registry.compose_registry(LIVE, {})
    inside = REPO / "scripts" / ".digichat-registry-test.json"
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.write_out(composed, str(inside))
    assert "repository" in str(refusal.value)
    assert not inside.exists()


def test_the_composed_registry_is_written_outside_the_repository(tmp_path):
    composed, _ = registry.compose_registry(LIVE, {})
    target = tmp_path / "registry.json"
    registry.write_out(composed, str(target))
    assert target.exists()
    assert oct(os.stat(str(target)).st_mode & 0o777) == "0o600"
    with target.open("r", encoding="utf-8") as handle:
        assert json.load(handle)["occ.digithings.ai"]["token"] == "tok-occ"
