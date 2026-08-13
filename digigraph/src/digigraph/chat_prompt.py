"""Build digigraph workflow prompts from OpenAI-compatible chat messages."""

from __future__ import annotations

import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from digigraph.models import ChatMessage

# Soft token budget for flattened chat history. Override via env; the default leaves
# headroom for the system prompt and downstream RAG context digisearch/digivault add on
# top of this flattened prompt.
_DEFAULT_MAX_HISTORY_TOKENS = 8000

_TYPE_TO_ROLE = {"human": "user", "ai": "assistant"}


def _trim_to_budget(turns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Token-budget-trim a flattened (role, content) turn list.

    Keeps the most recent turns and always starts on a user turn (LangChain's
    ``trim_messages`` convention — a trailing assistant-only tail with no matching user
    turn confuses a downstream model more than it helps). ``count_tokens_approximately``
    is an approximate counter (roughly chars/4) — fine for a soft budget, not exact.
    """
    if not turns:
        return turns
    max_tokens = int(
        os.environ.get("DIGI_CHAT_HISTORY_MAX_TOKENS", str(_DEFAULT_MAX_HISTORY_TOKENS))
    )
    as_messages = [
        HumanMessage(content=content) if role == "user" else AIMessage(content=content)
        for role, content in turns
    ]
    trimmed = trim_messages(
        as_messages,
        max_tokens=max_tokens,
        token_counter=count_tokens_approximately,
        strategy="last",
        start_on="human",
    )
    return [(_TYPE_TO_ROLE.get(m.type, m.type), str(m.content)) for m in trimmed]


def messages_to_workflow_prompt(messages: list[ChatMessage]) -> str:
    """Flatten OpenAI-style chat history into a single workflow ``prompt``.

    The research graph accepts one prompt string. Digichat (and other OpenAI-compat
    clients) send the full turn list on every request. Historically
    ``/v1/chat/completions`` joined only ``role=user`` contents and dropped
    assistant replies, which broke follow-ups that refer to prior answers
    ("elaborate on that", "what did you just say").

    Behavior:
    - Empty input → ``""``
    - Single user turn → content as-is (no role labels; preserves prior single-turn shape)
    - Multi-turn → ``User:`` / ``Assistant:`` dialogue in order
    - System / empty-content turns are omitted (project system prompt is separate)
    - ``role="tool"`` turns are also omitted, today deliberately: digichat's OpenAI-compat
      adapter never constructs one (verified: no ``role: "tool"`` construction anywhere
      under ``frontend/digichat/src/lib/adapters/digithings/``). If a caller ever DOES
      send tool-role history, this silent drop becomes real data loss — this function
      would then need explicit tool-turn support (e.g. a labeled "Tool result: ..." line),
      not a bigger message-list rewrite; see ``test_tool_role_messages_are_silently_omitted_today``.
    - Long multi-turn history is trimmed to ``DIGI_CHAT_HISTORY_MAX_TOKENS`` (default 8000)
      before flattening, keeping the most recent turns.
    """
    if not messages:
        return ""

    turns: list[tuple[str, str]] = []
    for m in messages:
        role = (m.role or "").strip().lower()
        if role not in ("user", "assistant"):
            continue
        content = (m.content or "").strip()
        if not content:
            continue
        turns.append((role, content))

    if not turns:
        # Fall back to last message content even if role was unexpected/empty filter.
        last = messages[-1].content or ""
        return last if isinstance(last, str) else str(last)

    if len(turns) == 1 and turns[0][0] == "user":
        return turns[0][1]

    turns = _trim_to_budget(turns)

    lines: list[str] = []
    for role, content in turns:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)
