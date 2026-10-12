"""The LuxAlgo trackers dataset allowlist is pinned client-side (DIG-1479).

This is the defect DIG-1479 exists for: ``TrackersLatestInput.dataset`` used to
be a bare ``NonEmptyStr``, so any dataset string the upstream published —
including ``congress-trades`` — validated client-side and was forwarded. The
upstream validating membership is not a legal classification. Membership is now
pinned to an explicit frozenset and a newly published dataset is refused until
a reviewed code change adds it.

What is pinned here:

* the exact six members, and that ``congress-trades`` is one of them because
  the business owner decided that on 2026-10-06 against Counsel's advice,
* that an unknown dataset string is refused on both trackers tools that take a
  dataset (the regression this issue exists for),
* that the orchestrator schemas for those two tools advertise the same six as an
  ``enum`` (DIG-1519), so the model reads the allowlist off the schema instead
  of paying a refused round trip, and that the two descriptions point at that
  enum as the limit,
* that the listing call still accepts ``dataset=None``, and that it is a
  pass-through to the upstream catalog rather than a view of the allowlist —
  which is why the listing's description may not claim the catalog is the six,
* that the risk-acceptance note stays attached to the ``congress-trades``
  entry, so a later reader cannot mistake the allowlist for legal clearance,
* and that no environment variable can widen the allowlist.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import httpx
import pytest
from pydantic import ValidationError

pytestmark = pytest.mark.unit

from digiquant.data.luxalgo import (  # noqa: E402
    LUXALGO_TRACKERS_ALLOWED_DATASETS,
    LuxAlgoClient,
    TrackersDatasetsInput,
    TrackersLatestInput,
    build_luxalgo_tool_dispatcher,
)
from digiquant.data.luxalgo.models import TrackersDatasetName  # noqa: E402
from digiquant.orchestrator_tools import (  # noqa: E402
    build_luxalgo_trackers_datasets_tool,
    build_luxalgo_trackers_latest_tool,
    build_luxalgo_trackers_ticker_tool,
)

MODELS_PY = Path(__file__).resolve().parents[2] / "digiquant/src/digiquant/data/luxalgo/models.py"

#: The five datasets with no 5 U.S.C. ch. 131 subchapter I filing behind them.
UNCLASSIFIED_RISK_DATASETS = (
    "insider-transactions",
    "thirteenf-holdings",
    "short-volume",
    "lobbying-filings",
    "gov-contracts",
)

#: The dataset Counsel classified as a 13107(c) report and advised refusing.
CONGRESS_TRADES = "congress-trades"


def test_the_allowlist_is_exactly_these_six_datasets() -> None:
    """Pin membership: adding a dataset must be a reviewed code change."""
    assert LUXALGO_TRACKERS_ALLOWED_DATASETS == frozenset(
        {*UNCLASSIFIED_RISK_DATASETS, CONGRESS_TRADES}
    )


def test_congress_trades_is_present_by_business_decision_not_by_counsel() -> None:
    """Its absence from the enum is deliberate — Counsel recommended refusal."""
    assert CONGRESS_TRADES in LUXALGO_TRACKERS_ALLOWED_DATASETS


@pytest.mark.parametrize("dataset", sorted(UNCLASSIFIED_RISK_DATASETS))
def test_the_five_datasets_without_a_ch131_filing_still_pass(dataset: str) -> None:
    """Containment must not break the datasets Counsel raised no objection to."""
    assert TrackersLatestInput(dataset=dataset).dataset == dataset
    assert TrackersDatasetsInput(dataset=dataset).dataset == dataset


@pytest.mark.parametrize(
    "dataset",
    [
        CONGRESS_TRADES,
        "insider-transactions",
        "thirteenf-holdings",
    ],
)
def test_every_allowlisted_dataset_passes_the_required_field(dataset: str) -> None:
    """``TrackersLatestInput.dataset`` is required, so pass the real thing."""
    assert TrackersLatestInput(dataset=dataset).dataset == dataset
    assert TrackersDatasetsInput(dataset=dataset).dataset == dataset


@pytest.mark.parametrize(
    "dataset",
    [
        "insider_transaction",  # underscore instead of hyphen
        "INSIDER-TRANSACTIONS",  # upstream ids are lower case; do not fold
        " insider-transactions",  # leading space is not the same id
        "insider-transactions ",  # trailing space
        "insider-transactions\n",  # control character
        "",  # empty
        "newly-published-dataset",  # the defect: unknown upstream id
        "congress/trades",  # the feed path, not a dataset id
        "congress-trades-v2",  # longer name is a different dataset
        "x",  # the loose placeholder value used in older tests
    ],
)
def test_an_unknown_dataset_is_refused(dataset: str) -> None:
    """The regression DIG-1479 exists for: unknown ids must not reach upstream."""
    with pytest.raises(ValidationError):
        TrackersLatestInput(dataset=dataset)
    with pytest.raises(ValidationError):
        TrackersDatasetsInput(dataset=dataset)


def test_the_listing_call_still_allows_no_dataset() -> None:
    """``trackers_datasets`` is the catalog call; omitting the filter is legal."""
    assert TrackersDatasetsInput().dataset is None
    assert TrackersDatasetsInput(dataset=None).dataset is None


def test_the_literal_alias_and_the_frozenset_agree() -> None:
    """Both spellings the same six names.

    The Literal is hand-written, not derived from the frozenset — a ``Literal``
    cannot be built from a frozenset — so this test is what catches drift
    between the two (DIG-1519 corrected the comment that claimed otherwise).
    """
    literal_members = set(TrackersDatasetName.__args__)
    assert literal_members == set(LUXALGO_TRACKERS_ALLOWED_DATASETS)


def test_the_orchestrator_schemas_advertise_the_allowlist() -> None:
    """DIG-1519: the model reads the six ids off the schema, not from a refusal.

    Without the enum a wrong ``dataset`` costs a round trip to discover it is
    refused. The enum is a shortcut, not the gate: the dispatcher still
    validates the payload, which is what the refusal tests below pin.
    """
    expected = sorted(LUXALGO_TRACKERS_ALLOWED_DATASETS)
    for builder in (
        build_luxalgo_trackers_datasets_tool,
        build_luxalgo_trackers_latest_tool,
    ):
        properties = builder()["function"]["parameters"]["properties"]
        assert properties["dataset"]["enum"] == expected, builder.__name__


def test_only_the_two_dataset_taking_tools_advertise_the_enum() -> None:
    """``trackers_ticker`` takes no ``dataset``, so it must not imply one."""
    properties = build_luxalgo_trackers_ticker_tool()["function"]["parameters"]["properties"]
    assert "dataset" not in properties


def test_the_dataset_taking_descriptions_point_at_the_enum_as_the_limit() -> None:
    """Both dataset-taking descriptions must hand the model the same limit.

    The enum is what makes the limit legible, so a description that left the
    reader guessing which ids are legal would undercut the change that added
    it. Deliberately checked for the pointer rather than for a specific
    sentence: the point is that the limit is stated, not how it is worded.

    ``luxalgo_trackers_ticker`` is out of scope here — it takes no ``dataset``.
    """
    for builder in (
        build_luxalgo_trackers_datasets_tool,
        build_luxalgo_trackers_latest_tool,
    ):
        description = builder()["function"]["description"]
        assert "enum" in description, builder.__name__


def test_the_catalog_listing_is_upstreams_and_is_not_the_allowlist() -> None:
    """Why the listing's description may not claim the catalog is the six.

    ``trackers_datasets`` with no ``dataset`` is a pass-through to the upstream
    catalog, which publishes datasets this service does not ingest, so the
    response legitimately names ids outside the allowlist. The allowlist bounds
    the ``dataset`` *filter*; it does not bound what the listing reports.

    This is the distinction DIG-1519's review caught the description blurring:
    trimming "and more" by claiming the six were the whole catalog would have
    replaced one false claim with another.
    """
    seen: dict[str, Any] = {}
    upstream_datasets = sorted(LUXALGO_TRACKERS_ALLOWED_DATASETS) + [
        "bills",
        "hearings",
        "options-flow",
    ]

    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        seen["arguments"] = body["params"]["arguments"]
        return httpx.Response(200, json={"result": {"datasets": upstream_datasets}})

    dispatcher = build_luxalgo_tool_dispatcher(
        client=LuxAlgoClient(transport=httpx.MockTransport(handler)),
    )
    result = json.loads(dispatcher("luxalgo_trackers_datasets", {})["content"])

    assert "dataset" not in seen["arguments"]
    assert set(upstream_datasets) - set(LUXALGO_TRACKERS_ALLOWED_DATASETS)
    assert result["data"]["datasets"] == upstream_datasets


def test_no_env_var_can_widen_the_allowlist(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Deny-only discipline: the environment cannot add a dataset either."""
    for name in (
        "DIGIQUANT_TRACKERS_ALLOWED_DATASETS",
        "DIGIQUANT_LUXALGO_TRACKERS_DATASETS",
        "LUXALGO_TRACKERS_ALLOWED_DATASETS",
        "DIGIQUANT_ALLOWED_TRACKERS_DATASETS",
    ):
        assert name not in TrackersLatestInput.model_config, name
        monkeypatch.setenv(name, "anything-else")
        with pytest.raises(ValidationError):
            TrackersLatestInput(dataset="anything-else")
    # Pin the field set: an env-backed default could only arrive as a new field.
    assert set(TrackersLatestInput.model_fields) == {
        "dataset",
        "ticker",
        "text",
        "where",
        "sort",
        "limit",
        "offset",
    }
    assert set(TrackersDatasetsInput.model_fields) == {"dataset"}


def test_the_risk_acceptance_note_stays_next_to_congress_trades() -> None:
    """A future contributor must not read the allowlist as a legal opinion.

    Counsel's stated reason (DIG-1479): digithings goes public in early 2027 and
    an unannotated ``congress-trades`` entry makes the repo look like it holds a
    clearance it does not hold.
    """
    source = MODELS_PY.read_text(encoding="utf-8")
    marker = f'"{CONGRESS_TRADES}"'
    assert marker in source, "the congress-trades entry must stay in the allowlist literal"
    comment_lines = [line for line in source.splitlines() if line.strip()]
    index = next(i for i, line in enumerate(comment_lines) if marker in line)
    preceding = "\n".join(comment_lines[max(0, index - 12) : index])
    assert "RISK-ACCEPTED" in preceding, "the congress-trades entry lost its risk-acceptance note"
    assert "Counsel" in preceding, "the note must say Counsel advised refusal"
    assert "not a legal clearance" in preceding


def test_the_old_upstream_validation_comment_is_gone() -> None:
    """Membership is a reviewed code change, not an upstream event."""
    source = MODELS_PY.read_text(encoding="utf-8")
    assert "validated upstream so a newly published dataset" not in source
    assert "never rejected client-side" not in source


def test_the_upstream_schema_description_no_longer_says_upstream_decides() -> None:
    """The tools advertise the pinned set to the model, not the reverse."""
    source = MODELS_PY.read_text(encoding="utf-8")
    assert "dataset membership itself is validated upstream" not in source
