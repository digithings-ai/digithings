"""An exclusive tenant with web search on keeps ``web_search`` end to end.

A tenant row with ``tools.exclusive: true``, an empty catalog and
``webSearch: true`` should leave the model exactly one real tool, the native
``web_search``, beside the session tools. digichat disables every built-in
family the catalog does not name (``exclusiveCatalogDisabledIds``) and sends
``X-Digi-Enable-Web-Search: 1``; digigraph must then:

* accept the turn when the license entitles ``hosted-web-search``, and
* keep ``web_search`` in the tool list offered to the model.

Without a license the turn is refused with 403; digichat retries it without
web search, which leaves only the session tools. That is the failure this
file pins, together with the stack helper that derives the public key the
license is checked against.
"""

from __future__ import annotations

import importlib.util
import os
import time
import uuid
from pathlib import Path
from unittest.mock import patch

import jwt
import pytest
from digigraph.server import app
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
PROJECT_CONFIG = REPO_ROOT / "infra" / "digichat-release" / "config" / "digiproject.yaml"
HELPER = REPO_ROOT / "apps" / "digithings-stack-cloudflare" / "container" / "license_public_key.py"

# digichat's BUILTIN_TOOL_FAMILIES (apps/digichat/src/lib/deploy-config/force-tool.ts)
# for an exclusive catalog that names neither family.
EXCLUSIVE_EMPTY_CATALOG_DISABLED = [
    "digisearch",
    "digisearch_semantic",
    "digisearch_fetch_all",
    "digisearch_web_search",
    "digivault",
    "digivault_search_notes",
    "digivault_get_note",
    "digivault_search_tag",
    "digivault_backlinks",
]

CHAT_PAYLOAD = {"model": "digigraph-rag", "messages": [{"role": "user", "content": "hi"}]}


def _load_helper():
    spec = importlib.util.spec_from_file_location("license_public_key", HELPER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _mint_license(services: list[str]) -> str:
    from digikey.license_verify import license_issuer_default

    priv_pem = os.environ["_PYTEST_DIGIKEY_PRIVATE_PEM"]
    license_id = f"lic-{uuid.uuid4().hex[:12]}"
    now = int(time.time())
    claims = {
        "sub": "example",
        "iss": license_issuer_default(),
        "aud": "digichat-license",
        "iat": now,
        "exp": now + 86400,
        "jti": license_id,
        "license_id": license_id,
        "tenant_slug": "example",
        "hosts": ["chat.example.com"],
        "kind": "digichat-license",
        "services": services,
    }
    return str(jwt.encode(claims, priv_pem, algorithm="RS256", headers={"kid": "t1"}))


@pytest.fixture(autouse=True)
def _derived_public_key(monkeypatch: pytest.MonkeyPatch) -> None:
    """Check licenses against the key the stack derives, not a pinned one."""
    derived = _load_helper().public_key_pem(os.environ["_PYTEST_DIGIKEY_PRIVATE_PEM"])
    assert "BEGIN PUBLIC KEY" in derived
    monkeypatch.setenv("DIGIKEY_PUBLIC_KEY_PEM", derived)
    monkeypatch.delenv("DIGI_TENANT_CORPUS_MAP", raising=False)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def _exclusive_web_headers(**extra: str) -> dict[str, str]:
    return {
        "X-Digi-Enable-Web-Search": "1",
        "X-Digi-Disabled-Tools": ",".join(EXCLUSIVE_EMPTY_CATALOG_DISABLED),
        **extra,
    }


def _ok_result():
    from digigraph.models import WorkflowResult

    return WorkflowResult(success=True, message="ok", backtest_result={})


def _offered_tool_names(*, enable_web_search: bool) -> set[str]:
    """Tool names research_node offers the model for this tenant shape."""
    from digigraph.models import WorkflowRequest
    from digigraph.orchestration import ToolContext
    from digigraph.orchestration.session_prefs_tools import SESSION_TOOL_NAMES
    from digigraph.project_config import DigiProjectConfig
    from digigraph.skills import get_tools_for_skills
    from digigraph.tool_policy import allowed_tool_names_for_workflow

    cfg = DigiProjectConfig.load(str(PROJECT_CONFIG))
    req = WorkflowRequest(
        prompt="x",
        enable_web_search=enable_web_search,
        disabled_tools=EXCLUSIVE_EMPTY_CATALOG_DISABLED,
    )
    allowed = allowed_tool_names_for_workflow(req, cfg)
    assert allowed is not None
    skills = list(cfg.get_enabled_skills())
    if enable_web_search:
        skills.append("web")
    skills.append("session")
    context = ToolContext(
        session_id=None,
        run_data_dir=None,
        index_name="default",
        index_config={},
        state={
            "enable_web_search": enable_web_search,
            "disabled_tools": EXCLUSIVE_EMPTY_CATALOG_DISABLED,
        },
        allowed_tool_names=allowed | SESSION_TOOL_NAMES,
    )
    names: set[str] = set()
    for tool in get_tools_for_skills(skills, context):
        fn = tool.get("function", tool) if isinstance(tool, dict) else {}
        names.add(str(fn.get("name", "")))
    return names


def test_derived_public_key_is_empty_without_a_usable_private_key() -> None:
    helper = _load_helper()
    assert helper.public_key_pem("") == ""
    assert helper.public_key_pem("-----BEGIN PRIVATE KEY-----\nnot a key\n") == ""


def test_licensed_exclusive_tenant_turn_keeps_web_search(client: TestClient) -> None:
    token = _mint_license(["hosted-web-search"])
    with patch("digigraph.server.run_digigraph_workflow") as run:
        run.return_value = _ok_result()
        r = client.post(
            "/v1/chat/completions",
            json=CHAT_PAYLOAD,
            headers=_exclusive_web_headers(**{"X-Digi-License": token}),
        )
    assert r.status_code == 200
    wf = run.call_args.args[0]
    assert wf.enable_web_search is True
    assert "web_search" not in (wf.disabled_tools or [])


def test_unlicensed_web_search_turn_is_refused(client: TestClient) -> None:
    """The live failure: no X-Digi-License, so the gate refuses web search."""
    with patch("digigraph.server.run_digigraph_workflow") as run:
        r = client.post("/v1/chat/completions", json=CHAT_PAYLOAD, headers=_exclusive_web_headers())
    run.assert_not_called()
    assert r.status_code == 403
    assert "hosted-web-search" in r.json()["message"]


def test_exclusive_tenant_offers_web_search_when_opted_in() -> None:
    names = _offered_tool_names(enable_web_search=True)
    assert "web_search" in names
    assert "session_set_language" in names


def test_without_opt_in_only_session_tools_remain() -> None:
    """What the model sees after digichat's silent retry without web search."""
    names = _offered_tool_names(enable_web_search=False)
    assert "web_search" not in names
    assert names, "session tools are always offered"
    assert all(n.startswith("session_") for n in names), sorted(names)
