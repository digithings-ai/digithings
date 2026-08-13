"""Cross-package contract: digigraph mirrors digivault no-prefix error strings."""

from __future__ import annotations

import inspect

import pytest
from digigraph.orchestration.builtin import (
    _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR,
    _DIGIVAULT_SEARCH_NO_PREFIX_ERROR,
)

from digivault import server as digivault_server

pytestmark = pytest.mark.unit


def test_digivault_no_prefix_error_strings_match_server_literals() -> None:
    """Substitution of either constant must not silently diverge from digivault."""
    src = inspect.getsource(digivault_server)
    assert _DIGIVAULT_SEARCH_NO_PREFIX_ERROR in src
    assert _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR in src
    assert _DIGIVAULT_SEARCH_NO_PREFIX_ERROR == (
        "path_prefix is required when the D1 backend is configured"
    )
    assert _DIGIVAULT_GET_NOTE_NO_PREFIX_ERROR == ("path_prefix is required for digivault_get_note")
