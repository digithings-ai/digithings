"""Exhaustive discovery of AI-run stock-portfolio accounts on X via xAI x_search (#658).

Runs several x_search passes (per-model + ecosystem + explicit candidate-handle
verification) so we enumerate ALL active accounts that post live equity portfolios with
named tickers — not just the obvious few. Prints each pass's output_text; a consolidated
@handle frequency is tallied by the caller from the logs. Throwaway; dispatch-only
workflow (needs XAI_API_KEY). Not imported by runtime code.
"""

from __future__ import annotations

import os
import sys

MODELS = ["Claude", "ChatGPT / GPT", "Grok", "Gemini", "DeepSeek", "Qwen", "Llama", "Mistral"]

# Candidate handles to verify existence/activity explicitly (user-suggested + variants).
CANDIDATES = [
    "theaiportfolios", "claudeportfolio", "claudeportfolios", "grkportfolio",
    "grokportfolio", "thegptinvestor", "chatgptportfolio", "gptportfolio",
    "geminiportfolio", "geminipicks", "deepseekportfolio", "deepseekfund",
    "qwenportfolio", "alejandroll10", "joinautopilot", "aierafund",
]


def _ask(client, model: str, prompt: str, label: str) -> None:
    print(f"\n################## {label} ##################", flush=True)
    try:
        r = client.responses.create(
            model=model,
            input=[{"role": "user", "content": prompt}],
            tools=[{"type": "x_search"}],
        )
        print((getattr(r, "output_text", "") or "")[:4000], flush=True)
    except Exception as exc:  # noqa: BLE001
        print(f"FAILED: {type(exc).__name__} {getattr(exc, 'status_code', '')} {str(exc)[:400]}",
              flush=True)


def main() -> int:
    key = os.environ.get("XAI_API_KEY", "").strip()
    if not key:
        print("XAI_API_KEY not set", file=sys.stderr)
        return 1
    from openai import OpenAI

    client = OpenAI(base_url="https://api.x.ai/v1", api_key=key)
    model = os.environ.get("XAI_SMOKE_MODEL", "grok-4.3")
    print(f"model={model}", flush=True)

    # 1) Per-model exhaustive enumeration.
    for m in MODELS:
        _ask(
            client, model,
            f"Search X exhaustively. List EVERY active account that frames itself as a "
            f"{m}-managed or {m}-driven STOCK/equity portfolio and posts named tickers + live "
            f"holdings/rebalances (not crypto-only, not generic commentary). For each give: exact "
            f"@handle, follower count, last-post date, and what it posts. Do not stop at the most "
            f"famous one — include smaller/newer accounts too. If none, say 'none'.",
            f"MODEL: {m}",
        )

    # 2) Ecosystem map.
    _ask(
        client, model,
        "Map the full ecosystem of AI/LLM-managed STOCK portfolio accounts on X linked to "
        "@alejandroll10 and the Autopilot (@joinautopilot) experiments, plus any similar "
        "multi-LLM equity-portfolio tracker projects. List every related @handle, which model "
        "each represents, and whether it is currently active. Be exhaustive.",
        "ECOSYSTEM",
    )

    # 3) Explicit candidate-handle verification.
    handles = ", ".join("@" + h for h in CANDIDATES)
    _ask(
        client, model,
        f"For each of these X handles, state whether it EXISTS and is ACTIVE (last-post date), "
        f"what it posts (live equity portfolio with named tickers? crypto? inactive?), follower "
        f"count, and which AI model it represents: {handles}. Be precise per handle.",
        "CANDIDATE VERIFICATION",
    )

    # 4) Final consolidated recommendation.
    _ask(
        client, model,
        "Now give the DEFINITIVE consolidated list of active X accounts that post AI/LLM-managed "
        "live EQUITY portfolios with named tickers, suitable to track daily. One line per account: "
        "`@handle | model | followers | last-post | posts-tickers? y/n`. Rank by usefulness as a "
        "cross-model stock-bias signal. Exclude crypto-only and inactive accounts.",
        "CONSOLIDATED",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
