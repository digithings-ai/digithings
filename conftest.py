"""Root conftest: optional path setup plus the paid-LLM guard for every test run.

Packages are found via the venv editable install.

Paid-LLM guard (2026-10-21)
---------------------------
An orphaned ``pytest -m unit`` run spent real money on Cheaper Inference: the test
process inherited ``CHEAPERINFERENCE_API_KEY`` from the shell that launched it (a
shell that had sourced ``~/Code/digithings/.env``), and digillm/digigraph prefer
Cheaper Inference whenever that variable is set (``digillm.client`` /
``digigraph.model_config``). pytest itself never loads ``.env``; the key only ever
arrives through the inherited environment.

So, unless a run opts in with ``DIGI_ALLOW_LIVE_LLM_TESTS=1``:

1. A non-empty ``CHEAPERINFERENCE_API_KEY`` stops the run before collection, with
   the fix in the message.
2. The other paid-provider keys are dropped from ``os.environ`` for the session.
   Tests that need a key set a fake one with ``monkeypatch``, as they already do.
3. Name resolution for paid LLM API hosts raises ``LiveLLMCallBlocked``, so a
   code path that forgot to mock its provider fails at once instead of billing.
   Loopback and every other host are untouched.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable
from typing import Any

import pytest

ALLOW_LIVE_ENV = "DIGI_ALLOW_LIVE_LLM_TESTS"

#: Fail-fast key: the house upstream, billed to Chris's account.
FAIL_FAST_KEYS = ("CHEAPERINFERENCE_API_KEY",)

#: Other paid-provider keys, scrubbed for the session (never printed).
SCRUBBED_KEYS = (
    "OPENROUTER_API_KEY",
    "OPENAI_API_KEY",
    "GEMINI_API_KEY",
    "GOOGLE_API_KEY",
    "XAI_API_KEY",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
    "GROQ_API_KEY",
    "TOGETHER_API_KEY",
    "FIREWORKS_API_KEY",
    "MISTRAL_API_KEY",
    "DEEPINFRA_API_KEY",
    "CEREBRAS_API_KEY",
    "OMNIROUTE_API_KEY",
)

#: Hosts whose API calls cost money. Suffix match: ``api.cheaperinference.com``
#: and ``platform.cheaperinference.com`` both hit ``cheaperinference.com``.
PAID_LLM_HOST_SUFFIXES = (
    "cheaperinference.com",
    "openrouter.ai",
    "api.openai.com",
    "openai.azure.com",
    "generativelanguage.googleapis.com",
    "aiplatform.googleapis.com",
    "api.deepseek.com",
    "api.x.ai",
    "api.anthropic.com",
    "api.groq.com",
    "api.together.xyz",
    "api.fireworks.ai",
    "api.mistral.ai",
    "api.deepinfra.com",
    "api.cerebras.ai",
    "api.sambanova.ai",
    "api.perplexity.ai",
    "integrate.api.nvidia.com",
    "ollama.com",
)


class LiveLLMCallBlocked(OSError):
    """Raised when a test tries to resolve a paid LLM API host."""


def live_llm_allowed(environ: Any = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(ALLOW_LIVE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_paid_llm_host(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    name = host.strip().rstrip(".").lower()
    return any(name == s or name.endswith("." + s) for s in PAID_LLM_HOST_SUFFIXES)


def _blocking_getaddrinfo(real: Callable[..., Any]) -> Callable[..., Any]:
    def getaddrinfo(host: Any, *args: Any, **kwargs: Any) -> Any:
        if is_paid_llm_host(host):
            raise LiveLLMCallBlocked(
                f"live LLM call blocked in tests: {host!r} is a paid API host. Mock the "
                f"provider, or set {ALLOW_LIVE_ENV}=1 for a deliberate live run."
            )
        return real(host, *args, **kwargs)

    getaddrinfo.__wrapped__ = real  # type: ignore[attr-defined]
    return getaddrinfo


@pytest.hookimpl(tryfirst=True)
def pytest_configure(config: pytest.Config) -> None:
    if live_llm_allowed():
        return
    present = [k for k in FAIL_FAST_KEYS if (os.environ.get(k) or "").strip()]
    if present:
        pytest.exit(
            f"{', '.join(present)} is set in the test environment; tests must not call "
            "Cheaper Inference (it bills real money). Run without it, e.g. "
            f"`env -u {present[0]} pytest ...`, or set {ALLOW_LIVE_ENV}=1 for a "
            "deliberate live run.",
            returncode=4,
        )
    for key in SCRUBBED_KEYS:
        os.environ.pop(key, None)
    if not hasattr(socket.getaddrinfo, "__wrapped__"):
        socket.getaddrinfo = _blocking_getaddrinfo(socket.getaddrinfo)
