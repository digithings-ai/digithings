"""Retrieval tool contract tests (Olympus #930 — tools/research-retrieval)."""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.research_retrieval import (
    ResearchCache,
    ResearchRetriever,
    portfolio_tool_allowed,
    query_portfolio,
    query_research,
    research_document_allowed,
)
from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


@pytest.mark.unit
class TestQueryResearch:
    def test_document_exact_date(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": {"headline": "Thu macro"},
                    },
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "Fri macro"},
                    },
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["source"] == "documents"
        assert out["as_of_date"] == "2026-06-19"
        assert out["payload"] == {"headline": "Fri macro"}

    def test_document_prior_published_fallback(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-18",
                        "document_key": "macro",
                        "payload": {"headline": "Thu macro"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            as_of_date=date(2026, 6, 19),
        )
        assert out["as_of_date"] == "2026-06-18"
        assert out["payload"]["headline"] == "Thu macro"

    def test_digest_from_daily_snapshots(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [
                    {
                        "date": "2026-06-19",
                        "snapshot": {"one_line_summary": "Risk-on"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="digest",
            as_of_date=date(2026, 6, 19),
        )
        assert out["source"] == "daily_snapshots"
        assert out["payload"] == {"one_line_summary": "Risk-on"}

    def test_segment_alias_maps_to_document_key(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "equity",
                        "payload": {"bias": "bullish"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            segment="equity",
        )
        assert out["document_key"] == "equity"
        assert out["payload"]["bias"] == "bullish"

    def test_default_as_of_is_latest_before_run_date(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "latest"},
                    }
                ]
            }
        )
        out = query_research(client, run_date=date(2026, 6, 20), document_key="macro")
        assert out["as_of_date"] == "2026-06-19"

    def test_cache_hit_for_latest_segment(self) -> None:
        client = FakeSupabaseClient(canned_reads={"documents": []})
        cache = ResearchCache(
            latest_segments={
                "macro": {
                    "date": "2026-06-19",
                    "document_key": "macro",
                    "payload": {"headline": "cached"},
                }
            },
            last_snapshots=[],
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            cache=cache,
        )
        assert out["payload"]["headline"] == "cached"
        assert out["cache_hit"] is True


@pytest.mark.unit
class TestFetchPriorDocument:
    def test_wraps_query_research_full_body(self) -> None:
        retriever = ResearchRetriever(
            client=FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": "2026-06-19",
                            "document_key": "macro",
                            "payload": {"headline": "full body"},
                        }
                    ]
                }
            ),
            run_date=date(2026, 6, 20),
            phase="atlas_edit",
        )
        assert retriever.fetch_prior_document("macro") == {"headline": "full body"}

    def test_section_path_navigation(self) -> None:
        retriever = ResearchRetriever(
            client=FakeSupabaseClient(
                canned_reads={
                    "documents": [
                        {
                            "date": "2026-06-19",
                            "document_key": "macro",
                            "payload": {"sections": {"rates": {"view": "higher"}}},
                        }
                    ]
                }
            ),
            run_date=date(2026, 6, 20),
            phase="atlas_edit",
        )
        assert retriever.fetch_prior_document("macro", section_path="/sections/rates") == {
            "view": "higher"
        }


@pytest.mark.unit
class TestQueryPortfolio:
    def test_returns_positions_nav_theses_lessons(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0},
                ],
                "nav_history": [
                    {"date": "2026-06-19", "nav": 1.02, "cash_pct": 5.0, "invested_pct": 95.0},
                ],
                "theses": [
                    {
                        "date": "2026-06-19",
                        "thesis_id": "t1",
                        "name": "AI capex",
                        "vehicle": "SMH",
                        "status": "ACTIVE",
                    }
                ],
                "decision_log": [
                    {
                        "id": "1",
                        "run_date": "2026-06-18",
                        "ticker": "SPY",
                        "status": "resolved",
                        "reflection": "waited for confirmation",
                    }
                ],
                "portfolio_metrics": [
                    {
                        "date": "2026-06-19",
                        "pnl_pct": 0.01,
                        "sharpe": 1.2,
                        "volatility": 0.1,
                        "max_drawdown": -0.05,
                        "alpha": 0.002,
                    }
                ],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
            watchlist=("SPY",),
        )
        assert out["as_of_date"] == "2026-06-19"
        assert out["positions"] == [{"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0}]
        assert out["nav"]["nav"] == 1.02
        assert out["theses"][0]["thesis_id"] == "t1"
        assert out["decision_lessons"][0]["reflection"] == "waited for confirmation"

    def test_ticker_filter(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-19", "ticker": "SPY", "weight_pct": 12.0},
                    {"date": "2026-06-19", "ticker": "QQQ", "weight_pct": 8.0},
                ],
                "nav_history": [],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
            ticker="SPY",
        )
        assert len(out["positions"]) == 1
        assert out["positions"][0]["ticker"] == "SPY"

    def test_prior_published_fallback(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-17", "ticker": "SPY", "weight_pct": 10.0},
                ],
                "nav_history": [],
                "theses": [],
                "decision_log": [],
            }
        )
        out = query_portfolio(
            client,
            run_date=date(2026, 6, 20),
            phase="h7_pm",
            as_of_date=date(2026, 6, 19),
        )
        assert out["as_of_date"] == "2026-06-17"


@pytest.mark.unit
class TestBlinding:
    def test_h5_analyst_blocks_portfolio(self) -> None:
        assert portfolio_tool_allowed("h5_analyst") is False
        out = query_portfolio(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            phase="h5_analyst",
        )
        assert "error" in out

    def test_h5_analyst_blocks_analyst_documents(self) -> None:
        assert research_document_allowed("h5_analyst", "analyst/SPY") is False
        out = query_research(
            FakeSupabaseClient(),
            run_date=date(2026, 6, 20),
            document_key="analyst/SPY",
            phase="h5_analyst",
        )
        assert "error" in out

    def test_h5_analyst_allows_macro_segment(self) -> None:
        assert research_document_allowed("h5_analyst", "macro") is True
        client = FakeSupabaseClient(
            canned_reads={
                "documents": [
                    {
                        "date": "2026-06-19",
                        "document_key": "macro",
                        "payload": {"headline": "ok"},
                    }
                ]
            }
        )
        out = query_research(
            client,
            run_date=date(2026, 6, 20),
            document_key="macro",
            phase="h5_analyst",
        )
        assert "error" not in out

    def test_h6_blocks_portfolio(self) -> None:
        assert portfolio_tool_allowed("h6_deliberation") is False

    def test_h7_allows_portfolio(self) -> None:
        assert portfolio_tool_allowed("h7_pm") is True

    def test_h1_allows_digest_and_portfolio(self) -> None:
        assert research_document_allowed("h1_thesis", "digest") is True
        assert portfolio_tool_allowed("h1_thesis") is True
