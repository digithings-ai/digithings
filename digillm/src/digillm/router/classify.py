"""Local scorer for digillm's router.

This is the utterance-centroid idea from aurelio-labs/semantic-router (MIT):
each category is a bag of example phrases, and the question is scored by
cosine similarity against those bags. The vectors are a deterministic feature
hash (Weinberger et al.), not a downloaded embedding model, so the decision
stays inside this process.

Why not the other open routers:

* Arch-Router-1.5B (Katanemo) matches this job — named routes, no retrain —
  but the April 2026 Katanemo Community License needs a separate commercial
  license from DigitalOcean, and a CPU Q4 call is about 1–3s before the real
  answer starts. The license's commercial path is to call the model through
  Arch Gateway, which digichat does not run (no proxy).
* RouteLLM (Apache-2.0) is a strong-vs-weak switch. Its recommended matrix-
  factorization router calls out for embeddings. The local BERT router is a
  binary classifier trained on one model pair, not Reasoning / Fast / Light.

Rules catch the obvious shapes (a greeting, a code block, a short lookup) so
the demo does not depend on a near-tie in the hash space. Anything else is
the centroid score. Nothing here opens a socket or reads a provider key.
"""

from __future__ import annotations

import math
import re

from digillm.router.types import RouterRoute

_DIM = 256
_WEAK = 0.12

_GREETING = re.compile(
    r"^(?:hi|hello|hey|yo|sup|thanks|thank you|thx|ok|okay|cool|"
    r"good morning|good evening|good night)[!.?\s]*$",
    re.IGNORECASE,
)
_CODE = re.compile(
    r"```|^[ \t]*(?:def |class |function |import |from |const |let |fn )"
    r"|\btraceback\b|\bstack trace\b"
    r"|\b(?:write|implement|debug|refactor)\b.{0,48}\b(?:function|class|script|code|component)\b",
    re.IGNORECASE | re.MULTILINE,
)
_REASONING = re.compile(
    r"\b(?:prove|proof|derive|theorem|step by step|chain of thought|"
    r"compare and contrast)\b|∫|∑|\\sqrt",
    re.IGNORECASE,
)
_LOOKUP = re.compile(
    r"^(?:what|who|when|where|which|define|convert|translate|how many|how much)\b",
    re.IGNORECASE,
)
_QUICK_MATH = re.compile(r"\d+\s*[-+*/^=]\s*\d+")
_NUMBERED = re.compile(r"(?m)^\s*1[.)].+\n\s*2[.)]")
_TOKEN = re.compile(r"[a-z0-9]+", re.IGNORECASE)

_STOP = frozenset(
    "a an the of to and or for in on at is are was be it this that with from as".split()
)


def _tokens(text: str) -> list[str]:
    return [token.lower() for token in _TOKEN.findall(text) if token.lower() not in _STOP]


def _hash_token(token: str) -> tuple[int, float]:
    # FNV-1a, 32-bit. Python's builtin hash is salted per process, so two
    # decisions of the same question would not match across the CLI boundary.
    hashed = 2166136261
    for byte in token.encode():
        hashed ^= byte
        hashed = (hashed * 16777619) & 0xFFFFFFFF
    index = hashed % _DIM
    sign = 1.0 if (hashed >> 8) & 1 else -1.0
    return index, sign


def _vector(text: str) -> list[float]:
    vec = [0.0] * _DIM
    for token in _tokens(text):
        index, sign = _hash_token(token)
        vec[index] += sign
    norm = math.sqrt(sum(value * value for value in vec))
    if norm == 0.0:
        return vec
    return [value / norm for value in vec]


def _centroid(route: RouterRoute) -> list[float]:
    texts = route.exemplar_texts()
    if not texts:
        return [0.0] * _DIM
    acc = [0.0] * _DIM
    for text in texts:
        vec = _vector(text)
        for index, value in enumerate(vec):
            acc[index] += value
    norm = math.sqrt(sum(value * value for value in acc))
    if norm == 0.0:
        return acc
    return [value / norm for value in acc]


def _cosine(left: list[float], right: list[float]) -> float:
    return sum(a * b for a, b in zip(left, right, strict=True))


def _has(routes: list[RouterRoute], route_id: str) -> bool:
    return any(route.id == route_id for route in routes)


def rule_route(text: str, routes: list[RouterRoute]) -> tuple[str, str, float] | None:
    """A structural hit, or None when the centroid should decide.

    The route id is returned only when that category is actually on offer, so
    an operator who dropped Light does not get a greeting forced onto it.
    """

    stripped = text.strip()
    if not stripped:
        return None
    if _GREETING.match(stripped) and _has(routes, "light"):
        return ("light", "Short greeting or acknowledgment.", 0.92)
    if _CODE.search(stripped) and _has(routes, "reasoning"):
        return ("reasoning", "Code or an error trace.", 0.9)
    long = len(stripped) > 600 or _NUMBERED.search(stripped) is not None
    if (_REASONING.search(stripped) or long) and _has(routes, "reasoning"):
        return ("reasoning", "Multi-step reasoning, math, or a long question.", 0.88)
    if (
        _QUICK_MATH.search(stripped)
        and len(stripped) < 120
        and _REASONING.search(stripped) is None
        and _has(routes, "fast")
    ):
        return ("fast", "Short calculation.", 0.84)
    if _LOOKUP.match(stripped) and len(stripped) < 200 and _has(routes, "fast"):
        return ("fast", "Short factual lookup.", 0.86)
    return None


def centroid_route(text: str, routes: list[RouterRoute]) -> tuple[str, str, float] | None:
    """Highest cosine above the weak-signal floor, or None."""

    query = _vector(text)
    if not any(query):
        return None
    scored: list[tuple[float, RouterRoute]] = []
    for route in routes:
        scored.append((_cosine(query, _centroid(route)), route))
    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, best = scored[0]
    if best_score < _WEAK:
        return None
    confidence = max(0.0, min(1.0, (best_score + 1.0) / 2.0))
    return (best.id, f"Closest to the {best.label} examples.", confidence)
