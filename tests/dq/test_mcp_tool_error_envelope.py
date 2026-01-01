"""MCP tool error envelope.

The audit found 114 copies of the same ``return json.dumps({"error": ...})``
body and 108 copies of the comment above it. They now share
:func:`digiquant.mcp_server._tool_error`; these tests pin the payload shape and
stop the copies coming back.
"""

from __future__ import annotations

import json
import pathlib

import pytest

from digiquant import mcp_server


@pytest.mark.unit
def test_error_envelope_names_the_exception_type_and_message() -> None:
    payload = json.loads(mcp_server._tool_error(ValueError("bad lookback")))
    assert payload == {"error": "ValueError: bad lookback"}


@pytest.mark.unit
def test_error_envelope_keeps_the_repr_quotes_of_a_key_error() -> None:
    assert json.loads(mcp_server._tool_error(KeyError("ticker"))) == {"error": "KeyError: 'ticker'"}


@pytest.mark.unit
def test_error_envelope_is_one_expression_in_the_module() -> None:
    """The per-tool envelope body must not be re-inlined."""
    source = pathlib.Path(mcp_server.__file__).read_text()
    assert source.count('json.dumps({"error": f"{type(exc).__name__}: {exc}"})') == 1
    # The per-site comment said nothing the helper does not; at most one
    # (shorter) survivor is allowed, where the body is deliberately different.
    assert source.count("surface as JSON to the caller, never crash") <= 1
