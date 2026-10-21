"""digillm's router. Local only: no provider call, no network."""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from digillm.router import RouterRoute, route_query
from digillm.router.decide import route_query as decide_route_query

pytestmark = pytest.mark.unit

_SRC = Path(__file__).resolve().parents[1] / "src"
_ROUTER = _SRC / "digillm" / "router"

ALLOWED = [
    "deepseek/deepseek-v4.1-flash-1017",
    "deepseek/deepseek-v4-pro",
    "google/gemini-3.1-flash-lite",
]
FALLBACK = "deepseek/deepseek-v4.1-flash-1017"


def test_categories_on_the_demo_allowlist() -> None:
    light = route_query(text="thanks!", allowed=ALLOWED, fallback=FALLBACK)
    fast = route_query(
        text="What is the capital of France?",
        allowed=ALLOWED,
        fallback=FALLBACK,
    )
    reasoning = route_query(
        text="Prove that the square root of 2 is irrational, step by step",
        allowed=ALLOWED,
        fallback=FALLBACK,
    )
    code = route_query(
        text="```python\ndef parse(data):\n    return json.loads(data)\n```",
        allowed=ALLOWED,
        fallback=FALLBACK,
    )
    assert light.route_id == "light"
    assert light.model == "google/gemini-3.1-flash-lite"
    assert fast.route_id == "fast"
    assert fast.model == "deepseek/deepseek-v4.1-flash-1017"
    assert reasoning.route_id == "reasoning"
    assert reasoning.model == "deepseek/deepseek-v4-pro"
    assert code.route_id == "reasoning"
    assert "capital" not in fast.reason.lower()
    assert "sqrt" not in reasoning.reason.lower()


def test_empty_question_uses_the_deployment_default() -> None:
    decision = route_query(text="   ", allowed=ALLOWED, fallback=FALLBACK)
    assert decision.model == FALLBACK
    assert "default" in decision.reason.lower()


def test_only_allowlisted_models_are_returned() -> None:
    decision = route_query(
        text="Prove this theorem step by step",
        allowed=["openai/gpt-5-mini"],
        fallback="openai/gpt-5-mini",
    )
    assert decision.model == "openai/gpt-5-mini"
    assert decision.reason == "Only one model is on the allowlist."


def test_operator_pin_overrides_the_preference_list() -> None:
    decision = route_query(
        text="hi",
        allowed=ALLOWED,
        fallback=FALLBACK,
        routes=[
            RouterRoute(
                id="light",
                label="Light",
                description="Simple chat.",
                model="deepseek/deepseek-v4.1-flash-1017",
            )
        ],
    )
    assert decision.route_id == "light"
    assert decision.model == "deepseek/deepseek-v4.1-flash-1017"


def test_pin_outside_the_allowlist_is_refused() -> None:
    with pytest.raises(Exception, match="allowlist"):
        route_query(
            text="hi",
            allowed=ALLOWED,
            fallback=FALLBACK,
            routes=[
                RouterRoute(
                    id="light",
                    label="Light",
                    description="Simple chat.",
                    model="openai/not-on-the-list",
                )
            ],
        )


def test_route_query_does_not_open_a_socket(monkeypatch: pytest.MonkeyPatch) -> None:
    def explode(*_args: object, **_kwargs: object) -> None:
        raise AssertionError("router opened a socket")

    monkeypatch.setattr(socket, "socket", explode)
    monkeypatch.setattr(socket, "create_connection", explode)
    decision = decide_route_query(
        text="Who wrote Hamlet?",
        allowed=ALLOWED,
        fallback=FALLBACK,
    )
    assert decision.route_id == "fast"


def test_package_source_does_not_call_a_provider() -> None:
    # Model ids in the preference list contain the "openai/" slug. That is a
    # catalog name, not the provider client. The scan is for a call or import.
    text = "\n".join(path.read_text() for path in _ROUTER.glob("*.py"))
    for banned in (
        "cheaperinference",
        "httpx",
        "urllib",
        "requests.get",
        "import openai",
        "from openai",
    ):
        assert banned not in text


def test_in_process_decision_is_sub_millisecond_at_the_median() -> None:
    samples: list[float] = []
    for _ in range(50):
        started = time.perf_counter()
        route_query(
            text="What is the capital of France?",
            allowed=ALLOWED,
            fallback=FALLBACK,
        )
        samples.append(time.perf_counter() - started)
    samples.sort()
    median = samples[len(samples) // 2]
    assert median < 0.005, f"median {median:.6f}s"


def test_cli_returns_a_decision_and_hides_a_bad_question() -> None:
    good = subprocess.run(
        [sys.executable, "-m", "digillm.router"],
        input=json.dumps(
            {
                "text": "thanks",
                "allowed": ALLOWED,
                "fallback": FALLBACK,
            }
        ),
        text=True,
        capture_output=True,
        cwd=_SRC.parent,
        env={**os.environ, "PYTHONPATH": str(_SRC)},
        check=False,
    )
    assert good.returncode == 0, good.stderr
    body = json.loads(good.stdout)
    assert body["route_id"] == "light"
    assert body["model"] == "google/gemini-3.1-flash-lite"
    assert "thanks" not in body["reason"].lower()

    secret = "z" * 9000
    bad = subprocess.run(
        [sys.executable, "-m", "digillm.router"],
        input=json.dumps({"text": secret, "allowed": ALLOWED, "fallback": FALLBACK}),
        text=True,
        capture_output=True,
        cwd=_SRC.parent,
        env={"PYTHONPATH": str(_SRC), "PATH": os.environ.get("PATH", "")},
        check=False,
    )
    assert bad.returncode == 2
    assert secret not in bad.stdout
    assert secret not in bad.stderr
    assert json.loads(bad.stdout) == {"error": "invalid_request"}
