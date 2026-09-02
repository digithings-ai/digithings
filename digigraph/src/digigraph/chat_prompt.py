"""Build digigraph workflow prompts from OpenAI-compatible chat messages."""

from __future__ import annotations

import logging
import os

from langchain_core.messages import AIMessage, HumanMessage
from langchain_core.messages.utils import count_tokens_approximately, trim_messages

from digigraph.models import ChatMessage

# Soft token budget for flattened chat history. Override via env; the default leaves
# headroom for the system prompt and downstream RAG context digisearch/digivault add on
# top of this flattened prompt.
_DEFAULT_MAX_HISTORY_TOKENS = 8000

_TYPE_TO_ROLE = {"human": "user", "ai": "assistant"}

logger = logging.getLogger(__name__)


def _max_history_tokens() -> int:
    """Read DIGI_CHAT_HISTORY_MAX_TOKENS, falling back to the default on a
    non-numeric value instead of letting int() raise ValueError and abort trimming."""
    raw = os.environ.get("DIGI_CHAT_HISTORY_MAX_TOKENS", str(_DEFAULT_MAX_HISTORY_TOKENS))
    try:
        return int(raw)
    except ValueError:
        logger.warning(
            "DIGI_CHAT_HISTORY_MAX_TOKENS=%r is not a valid integer; using default %d",
            raw,
            _DEFAULT_MAX_HISTORY_TOKENS,
        )
        return _DEFAULT_MAX_HISTORY_TOKENS


def _trim_to_budget(turns: list[tuple[str, str]]) -> list[tuple[str, str]]:
    """Token-budget-trim a flattened (role, content) turn list.

    Keeps the most recent turns and always starts on a user turn (LangChain's
    ``trim_messages`` convention — a trailing assistant-only tail with no matching user
    turn confuses a downstream model more than it helps). ``count_tokens_approximately``
    is an approximate counter (roughly chars/4) — fine for a soft budget, not exact.
    If trimming would empty the list (no user/human turn anchor), returns untrimmed turns.
    """
    if not turns:
        return turns
    max_tokens = _max_history_tokens()
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
    if not trimmed:
        # trim_messages(start_on="human") returns [] when the input has no
        # user/human turn to anchor on (e.g. an assistant-only tail after a
        # whitespace-only user turn was already filtered out upstream). Never
        # silently empty a non-empty input -- fall back to the untrimmed turns.
        return turns
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
      before flattening, keeping the most recent turns. If trim leaves a single user turn,
      that turn stays unlabeled (same as the single-turn fast path).
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
    # Trim can leave a single user turn (long thread → one surviving question).
    # Keep that unlabeled so ``last_user_turn`` does not treat ``User:`` as query text.
    if len(turns) == 1 and turns[0][0] == "user":
        return turns[0][1]

    lines: list[str] = []
    for role, content in turns:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)


def last_user_turn(prompt: str) -> str:
    """Current user string from a workflow ``prompt``.

    ``messages_to_workflow_prompt`` leaves a single user turn unlabeled and
    labels multi-turn history as ``User:`` / ``Assistant:`` blocks. ``/search``
    and ``/docs`` (#3418) must inject that current turn as the tool ``query``,
    not the whole flattened transcript.
    """
    text = (prompt or "").strip()
    if not text:
        return ""
    dialogue = text.startswith("User: ") and "\n\nAssistant: " in text
    last_marker = text.rfind("\n\nUser: ")
    if last_marker >= 0 and (dialogue or last_marker > 0):
        block = text[last_marker + len("\n\nUser: ") :]
        cut = block.find("\n\nAssistant: ")
        if cut >= 0:
            block = block[:cut]
        return block.strip()
    if dialogue:
        block = text[len("User: ") :]
        cut = block.find("\n\nAssistant: ")
        if cut >= 0:
            block = block[:cut]
        return block.strip()
    return text
