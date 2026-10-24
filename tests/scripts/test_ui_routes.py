"""Tests for scripts/ui_routes.py.

The counts here are the load-bearing assertions. The hosted total is 63 routes
after /app/tools/gloomberb joined the digiquant desk (DIG-3322). Before this
module existed that number was a claim in a document rather than something a
test could check. If someone adds or removes a page, this file fails and the
number is re-derived instead of remembered.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS = REPO_ROOT / "scripts"


def _load(name: str):
    """Load a script by path, registering it in sys.modules first.

    The registration must happen before exec_module: both scripts define
    dataclasses, and a dataclass body needs sys.modules[name] to exist.
    """
    if name not in sys.modules:
        spec = importlib.util.spec_from_file_location(name, SCRIPTS / f"{name}.py")
        module = importlib.util.module_from_spec(spec)
        sys.modules[name] = module
        spec.loader.exec_module(module)
    return sys.modules[name]


ui_routes = _load("ui_routes")
selfhost_target = _load("selfhost_target")


# --- non-vacuity controls -------------------------------------------------
# Without these, every zero below would be satisfied by an empty module.


def test_the_scripts_exist():
    assert (SCRIPTS / "ui_routes.py").is_file()
    assert (SCRIPTS / "selfhost_target.py").is_file()


def test_the_three_deployed_apps_are_declared():
    assert ui_routes.DEPLOYED_APPS == ("dashboard", "digithings-web", "digiquant-web")
    # Firing control: the exclusion list is not empty and does not overlap.
    assert ui_routes.REFERENCE_APPS == ("reference",)
    assert not set(ui_routes.DEPLOYED_APPS) & set(ui_routes.REFERENCE_APPS)


# --- the counts section 7 names ------------------------------------------


def test_route_count_is_63():
    report = ui_routes.build(target="hosted", env={})
    assert report["route_count"] == 63, report["apps"]


@pytest.mark.parametrize(
    ("app", "expected"),
    [("dashboard", 25), ("digithings-web", 25), ("digiquant-web", 13)],
)
def test_per_app_counts(app, expected):
    report = ui_routes.build(target="hosted", env={})
    assert len(report["apps"][app]["routes"]) == expected


def test_reference_app_is_enumerated_but_excluded_from_the_total():
    report = ui_routes.build(target="hosted", env={})
    reference = report["apps"]["reference"]
    assert reference["deployed"] is False
    assert reference["routes"], "reference should still be enumerated, not dropped"
    # An app that is never deployed must not be handed a URL, and must not be
    # handed an env var either. Offering one invents an obligation nobody has.
    assert reference["url"] is None
    assert reference["requires"] is None
    counted = sum(len(v["routes"]) for v in report["apps"].values() if v["deployed"])
    assert counted == 63
    # Firing control: the exclusion actually excludes something.
    assert len(reference["routes"]) > 0


# --- path derivation ------------------------------------------------------


def test_route_groups_are_stripped_from_the_path():
    # apps/digichat/app/(digichat)/embed/page.tsx -> /embed
    assert ui_routes.route_path(
        Path("apps/digichat/app/(digichat)/embed/page.tsx"),
        Path("apps/digichat/app"),
    ) == "/embed"


def test_dynamic_segments_keep_their_brackets():
    assert ui_routes.route_path(
        Path("apps/digiquant-web/app/strategies/[id]/page.tsx"),
        Path("apps/digiquant-web/app"),
    ) == "/strategies/[id]"


def test_root_route_is_a_single_slash():
    assert ui_routes.route_path(Path("apps/x/app/page.tsx"), Path("apps/x/app")) == "/"


def test_a_real_dynamic_route_is_present_in_the_enumeration():
    routes = ui_routes.enumerate_routes()["digiquant-web"].routes
    assert "/strategies/[id]" in routes


# --- URLs come from the resolver, not from a second table ----------------


def test_app_urls_are_taken_from_the_resolver(monkeypatch):
    """Prove the coupling. Delete a resolver URL and the app URL must go with it."""
    report = ui_routes.build(target="hosted", env={})
    original = selfhost_target.resolve

    def fake_resolve(*a, **k):
        res = original(*a, **k)
        for endpoint in res.endpoints:
            if endpoint["name"] == "quant":
                endpoint["url"] = None
        return res

    monkeypatch.setattr(ui_routes, "_load_resolver", lambda: type(
        "R", (), {"resolve": staticmethod(fake_resolve)}
    ))
    degraded = ui_routes.build(target="hosted", env={})
    assert report["apps"]["digiquant-web"]["url"]
    assert degraded["apps"]["digiquant-web"]["url"] is None


def test_hosted_urls_are_https_and_carry_the_target_base():
    report = ui_routes.build(target="hosted", env={})
    url = report["apps"]["digiquant-web"]["url"]
    assert url and url.startswith("https://digithings.ai")


def test_selfhost_urls_point_at_the_local_stack():
    report = ui_routes.build(target="selfhost", env={})
    url = report["apps"]["digiquant-web"]["url"]
    assert url and "digithings.localhost" in url


# --- a skip is never a pass ----------------------------------------------


def test_dashboard_is_skipped_on_selfhost_because_it_publishes_no_port():
    report = ui_routes.build(target="selfhost", env={})
    dash = report["apps"]["dashboard"]
    assert dash["url"] is None
    assert dash["requires"] == "DT_API_URL"


def test_dashboard_resolves_on_hosted():
    report = ui_routes.build(target="hosted", env={})
    assert report["apps"]["dashboard"]["url"]


def test_exit_code_is_one_when_a_deployed_app_has_no_url():
    rc = ui_routes.main(["--target", "selfhost", "--root", str(REPO_ROOT)])
    assert rc == 1, "a skipped deployed app must not exit 0"


def test_exit_code_is_zero_when_every_deployed_app_resolves():
    rc = ui_routes.main(["--target", "hosted", "--root", str(REPO_ROOT)])
    assert rc == 0


def test_text_output_lists_every_route():
    text = ui_routes.render_text(ui_routes.build(target="hosted", env={}))
    assert text.count("    /") >= 63
    assert "target: hosted" in text


def test_text_output_names_the_env_var_for_a_skip():
    text = ui_routes.render_text(ui_routes.build(target="selfhost", env={}))
    assert "SKIPPED - set DT_API_URL" in text


def test_base_url_override_moves_the_app_urls():
    report = ui_routes.build(target="hosted", env={"DT_BASE_URL": "https://edge.example.com"})
    assert report["apps"]["digiquant-web"]["url"].startswith("https://edge.example.com")


# --- agreement with the resolver's own contract view ---------------------


def test_route_count_agrees_with_the_resolver_contract():
    """The contract exists now. Both must agree the deployed set is this one."""
    contract_path, data = selfhost_target.load_contract(REPO_ROOT)
    if contract_path is None:
        pytest.skip("config/contract/ has not landed")
    report = ui_routes.build(target="selfhost", env={})
    assert report["route_count"] == 63
    assert ui_routes.DEPLOYED_APPS == ("dashboard", "digithings-web", "digiquant-web")