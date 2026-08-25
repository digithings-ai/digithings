"""Unit tests for Track B shared research corpus contracts (#2613)."""

from __future__ import annotations

from uuid import UUID

import pytest
from digiquant.olympus.research_corpus import (
    CorpusKey,
    CorpusKeyKind,
    ResearchCorpusKeyError,
    ResearchCorpusMissingError,
    ResearchCorpusPin,
    ResearchCorpusStore,
    corpus_pin_version_id,
    house_corpus_pin,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit


def test_parse_theme_asset_segment_keys() -> None:
    assert CorpusKey.parse("theme:AI").key == "theme:ai"
    assert CorpusKey.parse("asset:AAPL").key == "asset:aapl"
    assert CorpusKey.parse("segment:macro/rates").key == "segment:macro/rates"
    assert CorpusKey.parse("theme:ai").kind is CorpusKeyKind.THEME


def test_reject_unknown_kind() -> None:
    with pytest.raises(ResearchCorpusKeyError):
        CorpusKey.parse("user:alice")


def test_reject_tenant_markers_in_slug() -> None:
    with pytest.raises(ResearchCorpusKeyError):
        CorpusKey.parse("theme:user/alice")
    with pytest.raises(ResearchCorpusKeyError):
        CorpusKey.parse("asset:profile-bob")
    with pytest.raises(ResearchCorpusKeyError):
        CorpusKey.parse("segment:tenant.x")


def test_house_pin_deterministic_version() -> None:
    pin = house_corpus_pin("theme:ai", label="AI theme", summary="house default")
    assert pin.writer_role == "house"
    assert pin.version_id == corpus_pin_version_id("theme:ai", 1)
    assert isinstance(pin.version_id, UUID)


def test_pin_forbids_tenant_payload_fields() -> None:
    with pytest.raises(ValidationError):
        ResearchCorpusPin(
            version_id=corpus_pin_version_id("theme:ai"),
            corpus_key="theme:ai",
            writer_role="house",
            label="bad",
            payload={"profile_key": "user:alice"},
        )


def test_pin_version_must_match_key() -> None:
    with pytest.raises(ValidationError):
        ResearchCorpusPin(
            version_id=UUID("00000000-0000-4000-8000-000000000001"),
            corpus_key="theme:ai",
            writer_role="house",
            label="bad",
        )


def test_publish_if_missing_idempotent() -> None:
    store = ResearchCorpusStore()
    first = house_corpus_pin("asset:spy", label="SPY", summary="house")
    second = house_corpus_pin(
        "asset:spy",
        label="SPY overwrite attempt",
        summary="should not replace",
    )
    a = store.publish_if_missing(first)
    b = store.publish_if_missing(second)
    assert a.version_id == b.version_id
    assert b.label == "SPY"
    assert b.summary == "house"


def test_overlay_publish_if_missing_requires_flag() -> None:
    store = ResearchCorpusStore()
    pin = ResearchCorpusPin(
        version_id=corpus_pin_version_id("theme:energy"),
        corpus_key="theme:energy",
        writer_role="overlay_request",
        label="Energy",
    )
    with pytest.raises(ResearchCorpusKeyError):
        store.publish_if_missing(pin)
    published = store.publish_if_missing(pin, allow_overlay=True)
    assert published.writer_role == "overlay_request"
    # Second overlay request returns existing (no fork).
    again = store.publish_if_missing(
        ResearchCorpusPin(
            version_id=corpus_pin_version_id("theme:energy"),
            corpus_key="theme:energy",
            writer_role="overlay_request",
            label="Energy again",
        ),
        allow_overlay=True,
    )
    assert again.label == "Energy"


def test_load_missing_pin_fails_closed() -> None:
    store = ResearchCorpusStore()
    with pytest.raises(ResearchCorpusMissingError):
        store.load_by_version_id(UUID("00000000-0000-4000-8000-000000000099"))


def test_get_by_key_round_trip() -> None:
    store = ResearchCorpusStore()
    pin = house_corpus_pin("segment:europe", label="Europe")
    store.publish_if_missing(pin)
    loaded = store.get_by_key("segment:europe")
    assert loaded is not None
    assert loaded.version_id == pin.version_id
    assert store.load_by_version_id(pin.version_id).corpus_key == "segment:europe"


def test_extra_fields_forbidden() -> None:
    with pytest.raises(ValidationError):
        ResearchCorpusPin.model_validate(
            {
                "version_id": str(corpus_pin_version_id("theme:ai")),
                "corpus_key": "theme:ai",
                "writer_role": "house",
                "label": "x",
                "profile_id": "user:alice",
            }
        )
