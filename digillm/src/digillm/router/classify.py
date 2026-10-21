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
the centroid score. The phrases, the rule patterns, and the hash width live
in ``router_data.json``, which the digichat TypeScript port reads too.
Nothing here opens a socket or reads a provider key.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass

from digillm.router.data import RouterRule, router_table
from digillm.router.types import RouterRoute

_TABLE = router_table()
_DIM = _TABLE.dim
_WEAK = _TABLE.weak
_STOP = frozenset(_TABLE.stopwords)
_TOKEN = re.compile(_TABLE.token_pattern, re.IGNORECASE)


def _flags(spec: str) -> int:
    flags = 0
    if "i" in spec:
        flags |= re.IGNORECASE
    if "m" in spec:
        flags |= re.MULTILINE
    return flags


@dataclass(frozen=True)
class _CompiledRule:
    route: str
    op: str
    regex: re.Pattern[str]
    reason: str
    confidence: float
    max_chars: int | None
    unless: re.Pattern[str] | None
    numbered: re.Pattern[str] | None
    long_chars: int | None


def _compile_rule(rule: RouterRule) -> _CompiledRule:
    unless = None
    if rule.unless_pattern:
        unless = re.compile(rule.unless_pattern, _flags(rule.unless_flags))
    numbered = None
    if rule.numbered_pattern:
        numbered = re.compile(rule.numbered_pattern, _flags(rule.numbered_flags))
    return _CompiledRule(
        route=rule.route,
        op=rule.op,
        regex=re.compile(rule.pattern, _flags(rule.flags)),
        reason=rule.reason,
        confidence=rule.confidence,
        max_chars=rule.max_chars,
        unless=unless,
        numbered=numbered,
        long_chars=rule.long_chars,
    )


_RULES = tuple(_compile_rule(rule) for rule in _TABLE.rules)


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


def _over_max(rule: _CompiledRule, stripped: str) -> bool:
    return rule.max_chars is not None and len(stripped) >= rule.max_chars


def rule_route(text: str, routes: list[RouterRoute]) -> tuple[str, str, float] | None:
    """A structural hit, or None when the centroid should decide.

    The route id is returned only when that category is actually on offer, so
    an operator who dropped Light does not get a greeting forced onto it.
    """

    stripped = text.strip()
    if not stripped:
        return None
    for rule in _RULES:
        if not _has(routes, rule.route) or _over_max(rule, stripped):
            continue
        if rule.op == "match":
            if rule.regex.match(stripped):
                return (rule.route, rule.reason, rule.confidence)
            continue
        if rule.op == "search":
            if rule.unless is not None and rule.unless.search(stripped):
                continue
            if rule.regex.search(stripped):
                return (rule.route, rule.reason, rule.confidence)
            continue
        long = len(stripped) > (rule.long_chars or 0) or (
            rule.numbered is not None and rule.numbered.search(stripped) is not None
        )
        if rule.regex.search(stripped) or long:
            return (rule.route, rule.reason, rule.confidence)
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
