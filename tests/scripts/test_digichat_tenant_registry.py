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
OCC_ONLY = REPO / "infra" / "digichat-release" / "DIG-4488-occ-tenant-overlay.json"


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


def _occ_only_overlay():
    with OCC_ONLY.open("r", encoding="utf-8") as handle:
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


def test_the_occ_only_overlay_carries_one_tenant_and_no_credential():
    """The OCC-only overlay is the scoped apply: the OCC tenant, and nothing else."""
    overlay = registry.load_registry(_occ_only_overlay(), str(OCC_ONLY))
    assert sorted(overlay) == ["occ.digithings.ai"]
    entry = overlay["occ.digithings.ai"]
    assert "token" not in entry
    assert "tokenEnv" not in entry
    assert "mcp" not in entry
    assert "models" not in entry
    backend = entry.get("backend") or {}
    assert "digisearchIndex" not in backend
    assert "vaultPathPrefix" not in backend


def test_the_occ_only_overlay_carries_the_overlay_note():
    """An operator who opens only this file reads that it is an overlay.

    The note is a sibling of the tenant payload, so the composer never reads
    it: Guard 3 refuses an unknown key inside a tenant entry.
    """
    document = _occ_only_overlay()
    note = document.get("DIGICHAT_EMBED_TENANTS_note")
    assert isinstance(note, str)
    assert "OVERLAY, not the registry" in note
    assert "Never write this file to the worker secret" in note

    overlay = registry.load_registry(document, str(OCC_ONLY))
    assert sorted(overlay) == ["occ.digithings.ai"]
    assert "DIGICHAT_EMBED_TENANTS_note" not in overlay["occ.digithings.ai"]

    composed, report = registry.compose_registry(LIVE, overlay)
    assert sorted(composed) == sorted(LIVE)
    assert report["changed_paths"] == []


def test_the_occ_only_overlay_leaves_the_digithings_tenant_alone():
    overlay = registry.load_registry(_occ_only_overlay(), str(OCC_ONLY))
    composed, report = registry.compose_registry(LIVE, overlay)
    assert sorted(composed) == sorted(LIVE)
    assert composed["digithings.ai"] == LIVE["digithings.ai"]
    assert composed["digiquant.io"] == LIVE["digiquant.io"]
    assert not [p for p in report["changed_paths"] if p.startswith("digithings.ai")]


def test_the_occ_only_overlay_removes_the_models_section_from_the_kv_copy():
    overlay = registry.load_registry(_occ_only_overlay(), str(OCC_ONLY))
    composed, report = registry.compose_kv_registry(KV_LIVE, overlay)
    assert "models" not in composed["occ.digithings.ai"]
    assert "occ.digithings.ai.models" in report["removed_paths"]
    assert composed["occ.digithings.ai"]["tokenEnv"] == "OCC_INVITE_KEY"


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


def test_a_symlinked_spelling_of_the_repository_is_refused(tmp_path, monkeypatch):
    """The DIG-4588 failure under a symlinked path.

    A symlink that points INTO the repository resolves to a path inside
    it. Comparing the unresolved spelling against the repository root
    never matches, so the token-bearing registry would be written inside
    the checkout.
    """
    stand_in = tmp_path / "repo"
    stand_in.mkdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    monkeypatch.setattr(registry, "repo_root", lambda: str(stand_in))

    link = tmp_path / "link-to-repo"
    link.symlink_to(stand_in, target_is_directory=True)
    through_link = link / "registry.json"

    composed, _ = registry.compose_registry(LIVE, {})
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.write_out(composed, str(through_link))
    assert "repository" in str(refusal.value)
    assert not through_link.exists()
    assert not (stand_in / "registry.json").exists()

    # The other direction: a path spelled inside the repository is
    # refused even when it is a symlink pointing out of it, because
    # writing it would replace the symlink with a regular file that
    # carries tenant tokens inside the checkout.
    link_out = stand_in / "link-out.json"
    link_out.symlink_to(outside / "registry.json")
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.write_out(composed, str(link_out))
    assert "repository" in str(refusal.value)
    assert not (outside / "registry.json").exists()


def test_the_write_is_refused_when_the_repository_root_cannot_be_resolved(tmp_path, monkeypatch):
    """No resolvable root means no containment guarantee: fail closed."""
    monkeypatch.setattr(registry, "repo_root", lambda: None)
    target = tmp_path / "registry.json"
    composed, _ = registry.compose_registry(LIVE, {})
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.write_out(composed, str(target))
    assert "repository root" in str(refusal.value)
    assert not target.exists()


def test_the_admin_key_never_enters_the_argument_list(tmp_path, monkeypatch):
    """A command line is readable by every local process through ps."""
    key = "admin-key-value"
    key_file = tmp_path / "admin-key.txt"
    key_file.write_text(key + "\n", encoding="utf-8")

    seen = {}

    def fake_run(argv, cwd=None, stdin_text=None):
        seen["argv"] = list(argv)
        seen["stdin"] = stdin_text
        return 0, "\nhttp_code=200\n"

    monkeypatch.setattr(registry, "_run", fake_run)
    code, status, _body = registry.recycle_container(str(key_file), "https://example.invalid/reset")
    assert code == 0
    assert status == "200"
    assert key not in " ".join(seen["argv"])
    assert key not in "".join(seen["argv"])
    assert seen["stdin"] == "x-digi-admin-key: " + key + "\n"


def test_an_admin_key_file_holding_more_than_one_line_is_refused(tmp_path):
    key_file = tmp_path / "admin-key.txt"
    key_file.write_text("first-line\nsecond-line\n", encoding="utf-8")
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.recycle_container(str(key_file), "https://example.invalid/reset")
    assert "one line" in str(refusal.value)


def test_an_overlay_with_a_scalar_backend_is_refused_by_name():
    """The shape mistake is named, not raised as an AttributeError."""
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, {"digithings.ai": {"backend": "digigraph"}})
    assert "backend must be an object" in str(refusal.value)


def test_a_live_registry_with_a_scalar_backend_is_refused_by_name():
    broken = json.loads(json.dumps(LIVE))
    broken["digithings.ai"]["backend"] = "digigraph"
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(broken, {})
    assert "backend must be an object" in str(refusal.value)


# ---------------------------------------------------------------------------
# The Workers KV copy
# ---------------------------------------------------------------------------

# A fake Workers KV copy of the registry. It holds credential references by
# name, never values, exactly like the live copy.
KV_LIVE = {
    "occ.digithings.ai": {
        "slug": "occ",
        "gateMode": "ungated",
        # The legacy copy carries the same field, so the two fixtures
        # agree: the KV copy replaces the legacy entry for a host, and a
        # field that lives only in the legacy copy would stop being served.
        "attribution": False,
        "webSearch": False,
        "tokenEnv": "OCC_INVITE_KEY",
        "lockSessionControls": True,
        "backend": {
            "type": "digigraph",
            # Synthetic corpus routing, as in the legacy fixture above.
            "digisearchIndex": "tenant_corpus",
            "vaultPathPrefix": "clients/tenant-vault",
        },
        "mcp": {"servers": [{"id": "operator", "tokenEnv": "MCP_EDGE_KEY"}]},
        "tools": {"catalog": [{"id": "digisearch"}]},
        # The defect: a models section opens the model picker for a client
        # tenant. DIG-4486 refused the picker and DIG-4750 confirmed it.
        "models": {
            "default": "house/model",
            "available": ["house/model", "other/model"],
            "allowPicker": True,
        },
    },
}


def test_the_kv_compose_removes_the_occ_models_section():
    """The KV copy is the copy that is served, so it must carry no models."""
    composed, report = registry.compose_kv_registry(KV_LIVE, {})
    occ = composed["occ.digithings.ai"]
    assert "models" not in occ
    assert "occ.digithings.ai.models" in report["removed_paths"]
    assert "occ.digithings.ai.models" in report["changed_paths"]


def test_the_kv_compose_keeps_the_credential_reference_and_never_a_value():
    composed, _ = registry.compose_kv_registry(KV_LIVE, {})
    occ = composed["occ.digithings.ai"]
    assert occ["tokenEnv"] == "OCC_INVITE_KEY"
    assert "token" not in occ
    assert occ["mcp"]["servers"][0]["tokenEnv"] == "MCP_EDGE_KEY"
    assert "token" not in occ["mcp"]["servers"][0]


def test_the_kv_compose_keeps_the_base_corpus_routing_when_the_overlay_omits_it():
    overlay = {"occ.digithings.ai": {"backend": {"type": "digigraph"}}}
    composed, _ = registry.compose_kv_registry(KV_LIVE, overlay)
    backend = composed["occ.digithings.ai"]["backend"]
    assert backend["digisearchIndex"] == KV_LIVE["occ.digithings.ai"]["backend"]["digisearchIndex"]
    assert (
        backend["vaultPathPrefix"] == (KV_LIVE["occ.digithings.ai"]["backend"]["vaultPathPrefix"])
    )


def test_the_kv_compose_never_adds_a_tenant_the_kv_copy_does_not_have():
    overlay = {"occ.digithings.ai": {"slug": "occ"}, "digithings.ai": {"slug": "digithings"}}
    composed, report = registry.compose_kv_registry(KV_LIVE, overlay)
    assert sorted(composed) == ["occ.digithings.ai"]
    assert report["hosts_only_in_overlay"] == ["digithings.ai"]


def test_the_kv_compose_refuses_an_overlay_that_sets_models_for_the_occ_tenant():
    overlay = {"occ.digithings.ai": {"models": {"allowPicker": True}}}
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(KV_LIVE, overlay)
    assert "models" in str(refusal.value)


def test_the_legacy_compose_refuses_an_overlay_that_sets_models_for_the_occ_tenant():
    overlay = {"occ.digithings.ai": {"models": {"allowPicker": True}}}
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(LIVE, overlay)
    assert "models" in str(refusal.value)


def test_the_legacy_compose_removes_a_models_section_the_live_copy_carries():
    """A live copy that carries one is a defect, so it is removed."""
    broken = json.loads(json.dumps(LIVE))
    broken["occ.digithings.ai"]["models"] = {"allowPicker": True}
    composed, report = registry.compose_registry(broken, {})
    assert "models" not in composed["occ.digithings.ai"]
    assert "occ.digithings.ai.models" in report["removed_paths"]


def test_the_kv_compose_refuses_a_kv_copy_that_carries_a_token_value():
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["token"] = "tok-occ"
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "references by name only" in str(refusal.value)


def test_the_kv_compose_refuses_an_overlay_that_may_not_set_the_occ_corpus():
    overlay = {"occ.digithings.ai": {"backend": {"digisearchIndex": "other_index"}}}
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(KV_LIVE, overlay)
    assert "may not set digisearchIndex" in str(refusal.value)


def test_a_kv_copy_without_a_corpus_for_the_occ_tenant_is_refused():
    broken = json.loads(json.dumps(KV_LIVE))
    del broken["occ.digithings.ai"]["backend"]["digisearchIndex"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "does not route" in str(refusal.value)


def test_the_kv_plan_names_the_key_and_never_prints_a_value():
    composed, report = registry.compose_kv_registry(KV_LIVE, {})
    plan = registry.render_kv_plan(composed, report, "kv", "overlay", "embed-tenants", "ns-id")
    assert "embed-tenants" in plan
    assert "ns-id" in plan
    assert "occ.digithings.ai.models" in plan
    # The plan names the secret the copy needs, so the operator can check
    # that the Worker has it. A name is not a value.
    assert "OCC_INVITE_KEY" in plan
    assert "tok-occ" not in plan


def test_the_namespace_id_is_read_from_the_worker_config(tmp_path):
    config = tmp_path / "wrangler.toml"
    config.write_text(
        'name = "worker"\n'
        "\n"
        "[[kv_namespaces]]\n"
        'binding = "DIGICHAT_TENANTS_KV"\n'
        'id = "namespace-under-test"\n'
        "\n"
        "[vars]\n"
        'SOMETHING = "else"\n',
        encoding="utf-8",
    )
    assert registry.kv_namespace_id(str(tmp_path)) == "namespace-under-test"
    assert registry.kv_namespace_id(str(tmp_path), "OTHER_BINDING") is None


def test_the_namespace_id_is_unknown_when_the_config_cannot_be_read(tmp_path):
    assert registry.kv_namespace_id(str(tmp_path / "missing")) is None


def test_the_kv_document_travels_as_a_file_and_not_as_a_value(monkeypatch):
    """A command line is readable by every local process through ps."""
    seen = {}

    def fake_run(argv, cwd=None, stdin_text=None):
        seen["argv"] = list(argv)
        return 0, ""

    monkeypatch.setattr(registry, "_run", fake_run)
    temp = registry.write_temp_json({"occ.digithings.ai": {"slug": "occ"}})
    try:
        code, _out = registry.kv_key_put("embed-tenants", "ns-id", temp, ["wrangler"], ".")
    finally:
        os.unlink(temp)
    assert code == 0
    assert "--path" in seen["argv"]
    assert temp in seen["argv"]
    assert "embed-tenants" in seen["argv"]


def test_the_apply_writes_the_kv_copy_before_the_legacy_secret(tmp_path, monkeypatch):
    """The legacy secret alone changes nothing that is served.

    The KV copy wins for a tenant whose credential references resolve, so
    the KV copy is written first and the container is recycled last.
    """
    live = tmp_path / "live.json"
    live.write_text(json.dumps(LIVE), encoding="utf-8")
    kv = tmp_path / "kv.json"
    kv.write_text(json.dumps(KV_LIVE), encoding="utf-8")
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"occ.digithings.ai": {"slug": "occ"}}), encoding="utf-8")
    key_file = tmp_path / "admin-key.txt"
    key_file.write_text("admin-key-value\n", encoding="utf-8")

    calls = []
    documents = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        if "--path" in argv:
            path = argv[argv.index("--path") + 1]
            with open(path, "r", encoding="utf-8") as handle:
                documents.append(handle.read())
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(
        [
            "apply",
            "--live-from",
            str(live),
            "--kv-from",
            str(kv),
            "--kv-namespace-id",
            "ns-id",
            "--overlay",
            str(overlay),
            "--admin-key-file",
            str(key_file),
            "--worker-dir",
            str(tmp_path),
            "--confirm",
            "APPLY",
        ]
    )
    assert code == 0
    kinds = []
    for argv in calls:
        if argv[0] == "curl":
            kinds.append("recycle")
        elif "secret" in argv:
            kinds.append("secret")
        elif "kv" in argv:
            kinds.append("kv")
    assert kinds == ["kv", "secret", "recycle"]
    # The KV document that was written carries no models section and no
    # credential value.
    assert len(documents) == 1
    document = json.loads(documents[0])
    assert "models" not in document["occ.digithings.ai"]
    assert "token" not in document["occ.digithings.ai"]


def test_the_apply_refuses_a_kv_copy_that_carries_a_token_value(tmp_path, monkeypatch):
    live = tmp_path / "live.json"
    live.write_text(json.dumps(LIVE), encoding="utf-8")
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["token"] = "tok-occ"
    kv = tmp_path / "kv.json"
    kv.write_text(json.dumps(broken), encoding="utf-8")
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"occ.digithings.ai": {"slug": "occ"}}), encoding="utf-8")

    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(broken), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(
        [
            "apply",
            "--live-from",
            str(live),
            "--kv-from",
            str(kv),
            "--kv-namespace-id",
            "ns-id",
            "--overlay",
            str(overlay),
            "--confirm",
            "APPLY",
        ]
    )
    assert code == 2
    assert calls == []


# ---------------------------------------------------------------------------
# The guards a wrong implementation would break
# ---------------------------------------------------------------------------


def test_the_kv_compose_refuses_a_tenant_without_a_credential_reference():
    """A KV tenant with no token is served without one.

    The Worker replaces the legacy entry with the KV entry when the
    references resolve, so a tenant without a reference is served without
    its token, and the container refuses the whole registry.
    """
    broken = json.loads(json.dumps(KV_LIVE))
    del broken["occ.digithings.ai"]["tokenEnv"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "credential reference" in str(refusal.value)


def test_the_kv_compose_refuses_a_credential_reference_the_runtime_cannot_resolve():
    """An unresolved reference keeps the legacy copy: the write would do nothing."""
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["tokenEnv"] = "occ_invite_key"
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "not a secret name" in str(refusal.value)


def test_the_kv_compose_refuses_an_mcp_row_with_a_credential_value():
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["mcp"]["servers"][0]["token"] = ""
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "references by name only" in str(refusal.value)


def test_the_kv_compose_refuses_a_malformed_mcp_shape():
    for mcp in ("x", {"servers": 5}, {"servers": ["x"]}):
        broken = json.loads(json.dumps(KV_LIVE))
        broken["occ.digithings.ai"]["mcp"] = mcp
        with pytest.raises(registry.RegistryRefusal):
            registry.compose_kv_registry(broken, {})


def test_the_kv_compose_refuses_an_overlay_entry_that_is_not_an_object():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(KV_LIVE, {"digithings.ai": "slug"})
    assert "is not an object" in str(refusal.value)


def test_the_kv_compose_refuses_an_overlay_that_carries_a_secret():
    overlay = {"occ.digithings.ai": {"token": "tok-occ"}}
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(KV_LIVE, overlay)
    assert "token" in str(refusal.value)


def test_the_kv_compose_refuses_the_retired_corpus():
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["backend"]["digisearchIndex"] = "tenant_corpus,occ_tickets"
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "retired corpus" in str(refusal.value)


def test_a_corpus_index_that_is_not_a_string_is_refused_by_name():
    broken = json.loads(json.dumps(KV_LIVE))
    broken["occ.digithings.ai"]["backend"]["digisearchIndex"] = ["tenant_corpus"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(broken, {})
    assert "must be a string" in str(refusal.value)
    legacy = json.loads(json.dumps(LIVE))
    legacy["occ.digithings.ai"]["backend"]["digisearchIndex"] = ["tenant_corpus"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_registry(legacy, {})
    assert "must be a string" in str(refusal.value)


def test_an_empty_kv_registry_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry({}, {})
    assert "no tenant entries" in str(refusal.value)


def test_a_kv_entry_that_is_not_an_object_is_refused():
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry({"occ.digithings.ai": "slug"}, {})
    assert "is not an object" in str(refusal.value)


def test_the_kv_copy_may_not_drop_a_field_the_legacy_copy_carries():
    """The KV copy replaces the legacy entry, so a dropped field stops being served."""
    legacy, _ = registry.compose_registry(LIVE, {})
    kv = json.loads(json.dumps(KV_LIVE))
    del kv["occ.digithings.ai"]["attribution"]
    with pytest.raises(registry.RegistryRefusal) as refusal:
        registry.compose_kv_registry(kv, {}, legacy=legacy)
    assert "would drop" in str(refusal.value)
    assert "attribution" in str(refusal.value)


def test_the_kv_copy_may_leave_out_the_credential_value():
    """The token must not live in the KV copy, so its absence is not a drop."""
    legacy = {"occ.digithings.ai": {"slug": "occ", "token": "tok-occ"}}
    composed, _ = registry.compose_kv_registry(KV_LIVE, {}, legacy=legacy)
    assert composed["occ.digithings.ai"]["slug"] == "occ"


def test_a_note_in_front_of_the_document_does_not_break_the_read():
    text = 'npm warn exec\n{"occ.digithings.ai": {}}\n'
    assert registry._parse_json_document(text, "the live KV copy") == {"occ.digithings.ai": {}}
    with pytest.raises(registry.RegistryRefusal):
        registry._parse_json_document("not a document", "the live KV copy")


def test_the_kv_read_keeps_stdout_and_stderr_apart(monkeypatch):
    seen = {}

    def fake_run_read(argv, cwd=None):
        seen["argv"] = list(argv)
        return 0, '{"occ.digithings.ai": {}}', "npm warn exec"

    monkeypatch.setattr(registry, "_run_read", fake_run_read)
    code, out, err = registry.kv_key_get("embed-tenants", "ns-id", ["wrangler"], ".")
    assert code == 0
    assert json.loads(out) == {"occ.digithings.ai": {}}
    assert err == "npm warn exec"
    assert "--text" in seen["argv"]


def _apply_inputs(tmp_path, kv_document):
    live = tmp_path / "live.json"
    live.write_text(json.dumps(LIVE), encoding="utf-8")
    kv = tmp_path / "kv.json"
    kv.write_text(json.dumps(kv_document), encoding="utf-8")
    overlay = tmp_path / "overlay.json"
    overlay.write_text(json.dumps({"occ.digithings.ai": {"slug": "occ"}}), encoding="utf-8")
    key_file = tmp_path / "admin-key.txt"
    key_file.write_text("admin-key-value\n", encoding="utf-8")
    return live, kv, overlay, key_file


def _apply_argv(live, overlay, key_file, tmp_path, extra=None):
    argv = [
        "apply",
        "--live-from",
        str(live),
        "--kv-namespace-id",
        "ns-id",
        "--overlay",
        str(overlay),
        "--admin-key-file",
        str(key_file),
        "--worker-dir",
        str(tmp_path),
        "--confirm",
        "APPLY",
    ]
    if extra:
        argv = argv[:1] + extra + argv[1:]
    return argv


def test_the_apply_reads_the_live_kv_copy_and_writes_it(tmp_path, monkeypatch):
    """The write replaces the whole document, so the apply reads the live copy."""
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path))
    assert code == 0
    kinds = []
    for argv in calls:
        if argv[0] == "curl":
            kinds.append("recycle")
        elif "secret" in argv:
            kinds.append("secret")
        elif "kv" in argv:
            kinds.append("kv")
    assert kinds == ["kv", "secret", "recycle"]


def test_the_apply_refuses_a_live_kv_copy_it_cannot_read(tmp_path, monkeypatch):
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 1, "", "the namespace is not found"

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path))
    assert code == 2
    assert calls == []


def test_the_apply_refuses_a_stale_kv_copy(tmp_path, monkeypatch):
    """A copy that names other tenants is stale: writing it would drop them."""
    live, kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    stale = json.loads(json.dumps(KV_LIVE))
    stale["digiquant.io"] = {"slug": "digiquant", "tokenEnv": "DIGIQUANT_KEY"}
    kv.write_text(json.dumps(stale), encoding="utf-8")
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path, ["--kv-from", str(kv)]))
    assert code == 2
    assert calls == []


def test_the_apply_refuses_when_the_live_kv_copy_is_not_a_document(tmp_path, monkeypatch):
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, "npm warn exec The following package was not found", ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path))
    assert code == 2
    assert calls == []


def test_the_plan_only_apply_writes_nothing(tmp_path, monkeypatch):
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path, ["--plan-only"]))
    assert code == 0
    assert calls == []


def test_the_apply_puts_the_previous_kv_copy_back_when_the_secret_write_fails(
    tmp_path, monkeypatch
):
    """The two copies must never disagree about a tenant."""
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    documents = []
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        if "--path" in argv:
            path = argv[argv.index("--path") + 1]
            with open(path, "r", encoding="utf-8") as handle:
                documents.append(handle.read())
        if "secret" in argv:
            return 1, "the secret write failed"
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path))
    assert code == 1
    # The composed copy was written, then the previous copy was put back.
    assert len(documents) == 2
    assert json.loads(documents[1]) == KV_LIVE
    # The container was not recycled.
    assert not [argv for argv in calls if argv[0] == "curl"]


def test_the_apply_does_not_write_the_secret_when_the_kv_write_fails(tmp_path, monkeypatch):
    live, _kv, overlay, key_file = _apply_inputs(tmp_path, KV_LIVE)
    calls = []

    def fake_run(argv, cwd=None, stdin_text=None):
        calls.append(list(argv))
        if "kv" in argv:
            return 1, "the kv write failed"
        return 0, "\nhttp_code=200\n"

    def fake_kv_get(key, namespace_id, wrangler_cmd, worker_dir):
        return 0, json.dumps(KV_LIVE), ""

    monkeypatch.setattr(registry, "_run", fake_run)
    monkeypatch.setattr(registry, "kv_key_get", fake_kv_get)
    code = registry.main(_apply_argv(live, overlay, key_file, tmp_path))
    assert code == 1
    assert not [argv for argv in calls if "secret" in argv]
    assert not [argv for argv in calls if argv[0] == "curl"]
