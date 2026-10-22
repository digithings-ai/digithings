"""Stop pytest from calling a paid LLM unless the run opts in.

An orphaned ``pytest -m unit`` run spent real money on Cheaper Inference: the
process inherited ``CHEAPERINFERENCE_API_KEY`` from the shell that launched it,
and digillm/digigraph prefer Cheaper Inference whenever that variable is set.
pytest itself never loads ``.env``.

The guard is installed from the repo-root ``conftest.py`` and from a
``conftest.py`` in every package that carries ``[tool.pytest.ini_options]``.
Those packages are their own pytest rootdir, so they do not load the repo-root
conftest. A run that loads neither file is not covered.

Unless ``DIGI_ALLOW_LIVE_LLM_TESTS`` is ``1``, ``true``, ``yes`` or ``on``:

1. A non-empty ``CHEAPERINFERENCE_API_KEY`` stops the run before collection
   (exit 4). The message names the variable, never its value.
2. Other paid-provider keys are dropped from ``os.environ`` for the session.
3. ``socket.getaddrinfo`` raises ``LiveLLMCallBlocked`` for paid LLM API hosts.
   Loopback and every other host are untouched. This is a speed bump, not a
   boundary: an HTTPS proxy or a direct IP never goes through that name check.
"""

from __future__ import annotations

import os
import socket
from collections.abc import Callable, Mapping
from typing import Any

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


def live_llm_allowed(environ: Mapping[str, str] | None = None) -> bool:
    env = os.environ if environ is None else environ
    return (env.get(ALLOW_LIVE_ENV) or "").strip().lower() in {"1", "true", "yes", "on"}


def is_paid_llm_host(host: object) -> bool:
    if isinstance(host, bytes):
        host = host.decode("ascii", "ignore")
    if not isinstance(host, str):
        return False
    name = host.strip().rstrip(".").lower()
    return any(name == suffix or name.endswith("." + suffix) for suffix in PAID_LLM_HOST_SUFFIXES)


def fail_fast_message(environ: Mapping[str, str] | None = None) -> str | None:
    """Exit text when a house key is set, or None. The value is never included."""
    env = os.environ if environ is None else environ
    present = [key for key in FAIL_FAST_KEYS if (env.get(key) or "").strip()]
    if not present:
        return None
    return (
        f"{', '.join(present)} is set in the test environment; tests must not call "
        "Cheaper Inference (it bills real money). Run without it, e.g. "
        f"`env -u {present[0]} pytest ...`, or set {ALLOW_LIVE_ENV}=1 for a "
        "deliberate live run."
    )


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


def install() -> str | None:
    """Apply the guard. Return the exit message when the house key is set.

    The caller (a conftest ``pytest_configure``) turns that message into
    ``pytest.exit(..., returncode=4)``. Raising here would abort a pytest
    session that imported this module in order to test it.
    """
    if live_llm_allowed():
        return None
    message = fail_fast_message()
    if message is not None:
        for key in FAIL_FAST_KEYS:
            value = os.environ.get(key) or ""
            if value and value in message:
                raise RuntimeError("paid LLM guard message included a key value")
        return message
    for key in SCRUBBED_KEYS:
        os.environ.pop(key, None)
    if not hasattr(socket.getaddrinfo, "__wrapped__"):
        socket.getaddrinfo = _blocking_getaddrinfo(socket.getaddrinfo)  # type: ignore[method-assign]
    return None
