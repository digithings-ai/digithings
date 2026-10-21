"""The committed golden is the Python router's decision on parity_cases.json.

digichat's TypeScript port asserts the same file. A change to router_data.json
or the scorer has to update the golden, and the TypeScript test then fails
until the port matches.
"""

from __future__ import annotations

import json
from importlib.resources import files

import pytest

from digillm.router import RouterRoute, route_query

pytestmark = pytest.mark.unit


def test_python_router_matches_the_shared_golden() -> None:
    package = files("digillm.router")
    cases = json.loads(package.joinpath("parity_cases.json").read_text(encoding="utf-8"))
    expected = json.loads(package.joinpath("parity_expected.json").read_text(encoding="utf-8"))
    by_name = {item["name"]: item for item in expected["cases"]}
    assert len(by_name) == len(cases["cases"])
    for case in cases["cases"]:
        routes = None
        if case.get("routes"):
            routes = [RouterRoute.model_validate(item) for item in case["routes"]]
        decision = route_query(
            text=case["text"],
            allowed=case["allowed"],
            fallback=case["fallback"],
            routes=routes,
        )
        want = by_name[case["name"]]
        got = decision.model_dump()
        assert got["route_id"] == want["route_id"]
        assert got["label"] == want["label"]
        assert got["model"] == want["model"]
        assert got["reason"] == want["reason"]
        assert got["confidence"] == pytest.approx(want["confidence"], abs=1e-9)
        stripped = case["text"].strip().lower()
        if stripped:
            assert stripped not in got["reason"].lower()
