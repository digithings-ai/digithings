"""Graph nodes: research (LLM), backtest (DigiQuant). Phase 1."""

from __future__ import annotations

import json
import os
import re

import httpx

from digigraph.graph.state import WorkflowState
from digigraph.llm import chat_completion, get_model_for_mode

DIGIQUANT_URL = os.environ.get("DIGIQUANT_URL", "http://127.0.0.1:8001")

RESEARCH_SYSTEM = """You are a quant research assistant. Given a user idea for a trading strategy, respond with exactly a JSON object (no markdown, no extra text) with two keys:
- "strategy_name": snake_case name, e.g. mean_reversion_stat_arb, mean_reversion_tech
- "symbols": list of ticker symbols, e.g. ["AAPL", "MSFT", "GOOGL"]
Use the user message to infer strategy type and universe. Default to mean_reversion_tech and tech symbols if unclear."""


def _heuristic_fallback(prompt: str) -> tuple[str, list[str]]:
    """Fallback when LLM is unavailable or returns invalid JSON."""
    prompt_lower = prompt.lower()
    strategy_name = "mean_reversion_tech"
    if "mean-reversion" in prompt_lower or "mean reversion" in prompt_lower:
        strategy_name = "mean_reversion"
    if "stat-arb" in prompt_lower or "stat arb" in prompt_lower:
        strategy_name = "mean_reversion_stat_arb"
    symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    if "tech" in prompt_lower:
        symbols = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    return strategy_name, symbols


def research_node(state: WorkflowState) -> dict:
    """Data Science Family (Phase 1): use LLM to infer strategy and symbols from prompt."""
    prompt = state.get("prompt") or ""
    strategy_name = "mean_reversion_tech"
    symbols: list[str] = ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    research_note = ""

    try:
        content = chat_completion(
            model=get_model_for_mode(),
            messages=[
                {"role": "system", "content": RESEARCH_SYSTEM},
                {"role": "user", "content": prompt},
            ],
        )
        if content:
            # Strip markdown code block if present
            raw = re.sub(r"^```(?:json)?\s*", "", content).strip()
            raw = re.sub(r"\s*```$", "", raw)
            data = json.loads(raw)
            strategy_name = data.get("strategy_name", strategy_name)
            symbols = list(data.get("symbols", symbols))
            research_note = "LLM-extracted"
    except Exception:
        strategy_name, symbols = _heuristic_fallback(prompt)
        research_note = "heuristic-fallback"

    return {
        "strategy_name": strategy_name,
        "symbols": symbols,
        "research_note": research_note,
    }


def backtest_node(state: WorkflowState) -> dict:
    """Call DigiQuant run_backtest; write result or error into state."""
    strategy_name = state.get("strategy_name") or "mean_reversion_tech"
    symbols = state.get("symbols") or ["AAPL", "MSFT", "GOOGL", "NVDA", "META"]
    try:
        with httpx.Client(timeout=30.0) as client:
            r = client.post(
                f"{DIGIQUANT_URL.rstrip('/')}/run_backtest",
                json={"strategy_name": strategy_name, "symbols": symbols},
            )
            r.raise_for_status()
            backtest = r.json()
        return {"backtest_result": backtest, "error": None}
    except Exception as e:
        return {"backtest_result": None, "error": str(e)}
