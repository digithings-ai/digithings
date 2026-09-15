"""Unit tests for the digiclaw → digisearch scheduled tick (#4065, Task 8d)."""

from __future__ import annotations

import httpx
import pytest


@pytest.mark.unit
def test_tick_posts_with_service_jwt(monkeypatch: pytest.MonkeyPatch) -> None:
    import digibase.service_auth as svc

    from digiclaw import monitors_tick as mod

    monkeypatch.setenv("DIGISEARCH_URL", "http://127.0.0.1:8002")
    calls: dict = {}

    def fake_jwt(**k: object) -> str:
        calls.update(k)
        return "svc-jwt"

    monkeypatch.setattr(svc, "get_service_jwt", fake_jwt)
    seen: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["auth"] = request.headers.get("authorization")
        assert str(request.url) == "http://127.0.0.1:8002/v1/monitors/tick"
        return httpx.Response(200, json={"runs": []})

    monkeypatch.setattr(
        mod,
        "_post",
        lambda url, token: (
            httpx.Client(transport=httpx.MockTransport(handler))
            .post(url, headers={"authorization": f"Bearer {token}"})
            .json()
        ),
    )
    out = mod.run_due_monitors()
    assert seen["auth"] == "Bearer svc-jwt"
    assert calls.get("key_env") == "DIGICLAW_DIGIKEY_API_KEY"
    assert calls.get("scopes") == ("digisearch:query",)
    assert out == {"runs": 0, "failed": 0}


@pytest.mark.unit
def test_tick_counts_failed_runs(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiclaw import monitors_tick as mod

    payload = {
        "runs": [
            {"run_id": "r1", "status": "ok"},
            {"run_id": "r2", "status": "failed"},
            {"run_id": "r3", "status": "no_change"},
        ]
    }
    seen: dict = {}

    def fake_post(url: str, token: str) -> dict:
        seen.update(url=url, token=token)
        return payload

    monkeypatch.setattr(mod, "_post", fake_post)
    out = mod.run_due_monitors(digisearch_url="http://explicit:9999/", bearer_token="explicit")
    assert seen == {
        "url": "http://explicit:9999/v1/monitors/tick",
        "token": "explicit",
    }
    assert out == {"runs": 3, "failed": 1}


@pytest.mark.unit
def test_post_raises_for_http_error(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiclaw import monitors_tick as mod

    real_client = httpx.Client
    transport = httpx.MockTransport(lambda request: httpx.Response(401, json={"error": {}}))
    monkeypatch.setattr(httpx, "Client", lambda **kw: real_client(transport=transport, **kw))
    with pytest.raises(httpx.HTTPStatusError):
        mod._post("http://digisearch:8002/v1/monitors/tick", "svc-jwt")


@pytest.mark.unit
def test_dispatch_agent_maps_web_watch_tick(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiclaw.schedule_schema import AgentDefinition, AgentSchedule, ScheduleMode

    from digiclaw import cli, monitors_tick

    calls: list[str] = []
    monkeypatch.setattr(monitors_tick, "run_due_monitors", lambda: calls.append("tick"))

    def agent(name: str) -> AgentDefinition:
        return AgentDefinition(
            name=name,
            schedule=AgentSchedule(mode=ScheduleMode.CONTINUOUS, interval_seconds=60),
        )

    cli._dispatch_agent(agent("example-continuous"))
    assert calls == []
    cli._dispatch_agent(agent("web-watch-tick"))
    assert calls == ["tick"]
