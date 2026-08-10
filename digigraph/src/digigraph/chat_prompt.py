"""Build digigraph workflow prompts from OpenAI-compatible chat messages."""

from __future__ import annotations

from digigraph.models import ChatMessage


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

    lines: list[str] = []
    for role, content in turns:
        label = "User" if role == "user" else "Assistant"
        lines.append(f"{label}: {content}")
    return "\n\n".join(lines)
