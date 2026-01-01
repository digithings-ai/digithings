"""URL-table tests for the local self-host stack (DIG-4911).

The URL table is what an operator reads to see where each probe points. A
refused knob must not print a URL: printing the default one would show a
reachable address for a probe that never runs, which is the silent fallback
the refusal exists to prevent. The row carries the reason, so the operator
sees which knob is wrong.
"""

from __future__ import annotations

import pytest

from scripts.localstack import contracts, render

pytestmark = pytest.mark.unit


def _digigraph_check():
    return next(c for c in contracts.BUILTIN_CHECKS if c.name == "digigraph")


def test_the_url_table_shows_the_refusal_and_no_url():
    table = render.render_url_table(
        (_digigraph_check(),), {"DT_DIGIGRAPH_PORT": "8000@evil.com"}, "all"
    )
    assert "(invalid:" in table
    assert "DT_DIGIGRAPH_PORT" in table
    # The default URL is never printed for a refused knob: that would show a
    # reachable address for a probe that does not run.
    assert "http://127.0.0.1:8000/healthz" not in table


def test_the_url_table_still_prints_the_url_it_resolved():
    table = render.render_url_table((_digigraph_check(),), {"DT_DIGIGRAPH_PORT": "18000"}, "all")
    assert "http://127.0.0.1:18000/healthz" in table
    assert "(invalid:" not in table


def test_an_unconfigured_surface_is_still_reported_as_not_configured():
    """A refusal and a missing configuration are different things."""
    unconfigured = contracts.Check(
        name="r2-put-get",
        kind="roundtrip",
        url=None,
        profiles=("all",),
        source="test fixture",
        requires="DT_R2_URL",
    )
    table = render.render_url_table((unconfigured,), {}, "all")
    assert "(not configured: DT_R2_URL not set)" in table
    assert "(invalid:" not in table


def test_the_url_table_shows_a_refused_contract_row(tmp_path):
    """A refused contract row prints its reason and no URL.

    The row points at the built-in URL, so printing the default would show
    a reachable address for a probe that never runs.
    """
    contract = tmp_path / "config" / "contract"
    contract.mkdir(parents=True)
    (contract / "services.yaml").write_text(
        "services:\n  - name: digigraph\n    port: '8000@evil.com'\n",
        encoding="utf-8",
    )
    checks, _origin = contracts.load_checks(tmp_path)
    row = next(c for c in checks if c.name == "digigraph")

    table = render.render_url_table((row,), {}, "all")

    assert "(invalid:" in table
    assert "8000@evil.com" in table
    assert "http://127.0.0.1:8000/healthz" not in table


def test_the_url_table_never_prints_a_password_from_a_configured_url():
    """`dt urls` prints a configured URL, and that URL may carry a credential.

    A `requires` row is exempt from the loopback rule because it points at a
    service elsewhere, so userinfo can reach this table. The operator needs
    the address; the password never leaves the environment.
    """
    check = next(c for c in contracts.BUILTIN_CHECKS if c.requires == "DT_MCP_URL")
    table = render.render_url_table(
        (check,), {"DT_MCP_URL": "http://operator:s3cret@127.0.0.1:9000/mcp"}, "all"
    )
    assert "s3cret" not in table
    assert "***@" in table
    assert "127.0.0.1:9000" in table
