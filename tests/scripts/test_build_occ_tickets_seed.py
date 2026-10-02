"""Unit tests for scripts/build_occ_tickets_seed (no network, no embedding model)."""

from __future__ import annotations

import contextlib
import json
from pathlib import Path
from typing import Any

import pytest

from scripts import build_occ_tickets_seed as seed

pytestmark = pytest.mark.unit

SNAPSHOT_DATE = "2026-10-02"


def make_chunk(chunk_id: str = "zammad-1-1", doc_id: str = "zammad-1") -> Any:
    class FakeChunk:
        def __init__(self) -> None:
            self.id = chunk_id
            self.doc_id = doc_id
            self.content = "Subject line\n\nBody text with customer@example.test"
            self.metadata = {
                "number": "28312",
                "customer": "customer@example.test",
                "customer_name": "Jane Doe",
                "internal": False,
            }

    return FakeChunk()


def test_round_trip_preserves_every_field(tmp_path: Path) -> None:
    """write_snapshot -> read_snapshot is lossless for the fields the indexer needs."""
    rows = [
        seed._chunk_to_row(make_chunk("zammad-1-1", "zammad-1")),
        seed._chunk_to_row(make_chunk("zammad-2-1", "zammad-2")),
    ]
    payload = tmp_path / "occ_tickets.jsonl"
    seed.write_snapshot(rows, payload)

    chunks = seed.read_snapshot(payload)
    assert [c.id for c in chunks] == ["zammad-1-1", "zammad-2-1"]
    assert [c.doc_id for c in chunks] == ["zammad-1", "zammad-2"]
    assert chunks[0].metadata["customer"] == "customer@example.test"
    assert chunks[0].metadata["internal"] is False


def test_one_json_object_per_line_and_no_ascii_escaping(tmp_path: Path) -> None:
    payload = tmp_path / "occ_tickets.jsonl"
    seed.write_snapshot(
        [seed._chunk_to_row(make_chunk()), seed._chunk_to_row(make_chunk("b", "b"))], payload
    )

    lines = payload.read_text(encoding="utf-8").splitlines()
    assert len(lines) == 2
    assert json.loads(lines[0])["id"] == "zammad-1-1"


def test_read_snapshot_skips_blank_lines(tmp_path: Path) -> None:
    payload = tmp_path / "occ_tickets.jsonl"
    row = json.dumps(seed._chunk_to_row(make_chunk()))
    payload.write_text(f"{row}\n\n{row}\n", encoding="utf-8")

    assert len(seed.read_snapshot(payload)) == 2


@pytest.mark.parametrize(
    ("line", "expected_fragment"),
    [
        ("{not json", "invalid JSON"),
        ('{"id": "x"}', "missing ['content', 'doc_id']"),
    ],
)
def test_read_snapshot_rejects_malformed_rows_with_line_numbers(
    tmp_path: Path, line: str, expected_fragment: str
) -> None:
    payload = tmp_path / "occ_tickets.jsonl"
    payload.write_text(f"{line}\n", encoding="utf-8")

    with pytest.raises(SystemExit) as excinfo:
        seed.read_snapshot(payload)

    message = str(excinfo.value)
    assert "occ_tickets seed:" in message
    assert ":1:" in message
    assert expected_fragment in message


def test_ingest_refuses_a_missing_snapshot(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="no snapshot at"):
        seed.ingest_snapshot(tmp_path / "absent.jsonl", "occ_tickets")


def test_ingest_refuses_an_empty_snapshot(tmp_path: Path) -> None:
    payload = tmp_path / "occ_tickets.jsonl"
    payload.write_text("\n\n", encoding="utf-8")

    with pytest.raises(SystemExit, match="holds no articles"):
        seed.ingest_snapshot(payload, "occ_tickets")


def test_ingest_delegates_to_the_shared_multilingual_helper(tmp_path: Path, monkeypatch) -> None:
    """The snapshot path must use the live backfill's provider-pinned writer."""
    payload = tmp_path / "occ_tickets.jsonl"
    seed.write_snapshot([seed._chunk_to_row(make_chunk())], payload)
    seen: dict[str, Any] = {}

    @contextlib.contextmanager
    def fake_multilingual_index(index_name, chunks):
        seen["index_name"] = index_name
        seen["count"] = len(chunks)
        yield None

    monkeypatch.setattr("scripts.index_occ_tickets.multilingual_index", fake_multilingual_index)

    assert seed.ingest_snapshot(payload, "occ_tickets_custom") == 1
    assert seen == {"index_name": "occ_tickets_custom", "count": 1}


def test_build_refuses_to_write_an_empty_payload(tmp_path: Path, monkeypatch) -> None:
    """A failed Zammad crawl must not replace a good snapshot with an empty one."""
    monkeypatch.setenv("ZAMMAD_API_TOKEN", "token")

    class FakeClient:
        def list_tickets(self) -> list[dict[str, Any]]:
            return []

    monkeypatch.setattr("scripts.zammad_mcp.client.ZammadClient", FakeClient)
    out = tmp_path / "occ_tickets.jsonl"

    with pytest.raises(SystemExit, match="refusing to write an empty payload"):
        seed.build_snapshot(out, None, SNAPSHOT_DATE)

    assert not out.exists()


def test_build_requires_a_zammad_token(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.delenv("ZAMMAD_API_TOKEN", raising=False)

    with pytest.raises(SystemExit, match="ZAMMAD_API_TOKEN is not set"):
        seed.build_snapshot(tmp_path / "occ_tickets.jsonl", None, SNAPSHOT_DATE)


def test_max_tickets_must_be_positive(tmp_path: Path) -> None:
    with pytest.raises(SystemExit, match="--max-tickets must be a positive integer"):
        seed.main(["--max-tickets", "0", "--out", str(tmp_path / "occ_tickets.jsonl")])


def test_committed_snapshot_parses_and_covers_tickets() -> None:
    """The payload the stack image ships must be readable and non-trivial."""
    payload = Path(seed.DEFAULT_OUT)
    if not payload.is_file():
        pytest.skip("occ_tickets snapshot not present in this checkout")

    raw = payload.read_text(encoding="utf-8")
    lines = [line for line in raw.splitlines() if line.strip()]
    rows = [json.loads(line) for line in lines]

    # A truncated or half-regenerated payload still parses, so bound it from
    # both ends: the live corpus is ~900 articles and the JSONL is ~1.5 MB.
    # `> 100` alone would pass on a 5% slice.
    assert len(rows) > 500, "snapshot is suspiciously small — was the refresh truncated?"
    assert len(raw.encode("utf-8")) > 500_000, "snapshot byte count is far below the shipped corpus"
    assert not raw.endswith("\n\n"), "trailing blank line suggests an interrupted write"

    assert all({"id", "doc_id", "content", "metadata"} <= row.keys() for row in rows)
    assert len({row["id"] for row in rows}) == len(rows), "chunk ids must be unique"

    # Every field the chat surface renders or filters on. Losing one silently
    # degrades the ticket view rather than failing loudly at query time.
    required_metadata = {
        "number",
        "customer",
        "customer_name",
        "internal",
        "group",
        "organization",
        "owner",
        "priority",
        "article_index",
        "article_type",
    }
    missing = {key for row in rows for key in required_metadata if key not in row["metadata"]}
    assert not missing, f"snapshot rows missing metadata the chat surface uses: {sorted(missing)}"

    assert all(row["content"].strip() for row in rows), "empty article body in snapshot"
    assert any(row["metadata"].get("internal") for row in rows), "internal notes must be tagged"
    assert any(row["metadata"].get("customer") for row in rows), "demo mode keeps customer emails"
