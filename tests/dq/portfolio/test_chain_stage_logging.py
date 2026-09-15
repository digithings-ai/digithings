"""The chain CLI must narrate its stages, and must actually configure logging (#4116).

The entry point used to emit nothing below WARNING because it never configured a
handler, so a multi-hour run was silent in CI. These tests pin the handler setup and
the stage markers that make ``artifacts/run.log`` readable while the run proceeds.
"""

from __future__ import annotations

import logging

import pytest
from digiquant.portfolio import chain as chain_mod

pytestmark = pytest.mark.unit


@pytest.fixture
def clean_root_logger():
    root = logging.getLogger()
    saved_handlers = list(root.handlers)
    saved_level = root.level
    for handler in list(root.handlers):
        root.removeHandler(handler)
    try:
        yield root
    finally:
        for handler in list(root.handlers):
            root.removeHandler(handler)
        for handler in saved_handlers:
            root.addHandler(handler)
        root.setLevel(saved_level)


def test_cli_logging_is_configured_once_on_stdout(
    clean_root_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.delenv("DIGIQUANT_LOG_LEVEL", raising=False)
    clean_root_logger.handlers.clear()

    chain_mod._configure_cli_logging()
    assert len(clean_root_logger.handlers) == 1

    chain_mod._configure_cli_logging()

    assert clean_root_logger.level == logging.INFO
    assert len(clean_root_logger.handlers) == 1


def test_cli_logging_honours_the_env_level(
    clean_root_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_LOG_LEVEL", "DEBUG")

    chain_mod._configure_cli_logging()

    assert clean_root_logger.level == logging.DEBUG


def test_cli_logging_ignores_an_unknown_level(
    clean_root_logger: logging.Logger, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_LOG_LEVEL", "chatty")

    chain_mod._configure_cli_logging()

    assert clean_root_logger.level == logging.INFO


def test_stage_markers_report_position_and_elapsed(caplog: pytest.LogCaptureFixture) -> None:
    started = chain_mod._stage_start(2, 5, "research")

    with caplog.at_level(logging.INFO, logger="digiquant.portfolio.chain"):
        chain_mod._stage_done(2, 5, "research", started)

    messages = [record.getMessage() for record in caplog.records]
    assert any("[2/5] research" in message for message in messages)
    assert any("done in" in message for message in messages)
