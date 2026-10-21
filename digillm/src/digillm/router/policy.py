"""Built-in categories and how they bind to a deployment's allowlist.

Auto on an unconfigured digichat install is ``deepseek/deepseek-v4.1-flash-1017``.
The router does not replace that default. It picks among Reasoning, Fast, and
Light, and each category walks a preference list until it finds an id the
deployment actually allows. An id that is not allowed is never returned.
"""

from __future__ import annotations

from digillm.router.types import RouterError, RouterRoute

# Preference order is the demo catalog in
# apps/digichat/config/digichat-deploy-models.json. First allowlisted id wins.
# Operators pin a different id with ``routes[].model``.
ROUTE_MODEL_PREFERENCES: dict[str, tuple[str, ...]] = {
    "reasoning": (
        "deepseek/deepseek-v4-pro",
        "openai/gpt-6-luna",
        "openai/gpt-5.6-luna",
        "minimax/minimax-m3",
        "google/gemini-3.7-flash",
    ),
    "fast": (
        "deepseek/deepseek-v4.1-flash-1017",
        "z-ai/glm-5.3-flash",
        "qwen/qwen3.8-flash",
        "xiaomi/mimo-v2.6-flash",
        "openai/gpt-5-mini",
    ),
    "light": (
        "google/gemini-3.1-flash-lite",
        "qwen/qwen3.8-flash",
        "openai/gpt-5-mini",
        "openai/gpt-oss-120b",
        "deepseek/deepseek-v4.1-flash-1017",
    ),
}

# Exemplars are the utterance bags the scorer compares against. They stay in
# the library: a deployment config can add phrases, it does not have to
# restate these.
_BUILTIN_EXEMPLARS: dict[str, tuple[str, ...]] = {
    "reasoning": (
        "Prove that the square root of 2 is irrational, step by step",
        "Compare these two designs and recommend one",
        "Refactor this function and explain its complexity",
        "Derive the gradient of the loss",
        "Plan the migration across the three services",
    ),
    "fast": (
        "What is the capital of France?",
        "Who wrote Hamlet?",
        "Convert 10 km to miles",
        "Define idempotent",
        "When did the Berlin wall fall?",
    ),
    "light": (
        "Hi",
        "Thanks",
        "Good morning",
        "Rewrite this sentence to sound friendlier",
        "Say that more briefly",
    ),
}

BUILTIN_ROUTES: tuple[RouterRoute, ...] = (
    RouterRoute(
        id="reasoning",
        label="Reasoning",
        description="Hard multi-step reasoning, math, code, and planning.",
        exemplars=list(_BUILTIN_EXEMPLARS["reasoning"]),
    ),
    RouterRoute(
        id="fast",
        label="Fast",
        description="A short factual lookup or a quick answer.",
        exemplars=list(_BUILTIN_EXEMPLARS["fast"]),
    ),
    RouterRoute(
        id="light",
        label="Light",
        description="Simple chat, greetings, and light rewrites.",
        exemplars=list(_BUILTIN_EXEMPLARS["light"]),
    ),
)


def resolve_routes(overrides: list[RouterRoute] | None) -> list[RouterRoute]:
    """Built-in categories, with an operator route of the same id overlaid.

    A route id the library does not know is appended. Omitting ``overrides``
    keeps Reasoning, Fast, and Light.
    """

    if not overrides:
        return [route.model_copy(deep=True) for route in BUILTIN_ROUTES]
    by_id = {route.id: route.model_copy(deep=True) for route in BUILTIN_ROUTES}
    order = [route.id for route in BUILTIN_ROUTES]
    extras: list[RouterRoute] = []
    seen: set[str] = set()
    for override in overrides:
        if override.id in seen:
            raise RouterError(f"duplicate router route {override.id}")
        seen.add(override.id)
        current = by_id.get(override.id)
        if current is None:
            extras.append(override.model_copy(deep=True))
            continue
        data = current.model_dump()
        patch = override.model_dump(exclude_unset=True)
        # An explicit empty exemplar list means "use only the description",
        # not "keep the built-in phrases". model_dump includes the default
        # empty list, so treat a non-empty list as the replacement and an
        # empty one as "leave the built-ins" when the caller used the model
        # defaults. Callers that want no extra phrases pass the description
        # only and we still score that description.
        if not patch.get("exemplars"):
            patch.pop("exemplars", None)
        data.update(patch)
        by_id[override.id] = RouterRoute.model_validate(data)
    return [by_id[route_id] for route_id in order] + extras


def bind_model(
    route: RouterRoute,
    allowed: list[str],
    fallback: str,
) -> str:
    """The model this category will call. Never an id outside ``allowed``
    when that list is non-empty."""

    allow = [item.strip() for item in allowed if item.strip()]
    allow_set = set(allow)
    pinned = (route.model or "").strip()
    if pinned:
        if allow_set and pinned not in allow_set:
            raise RouterError(
                f"router route {route.id} pins {pinned}, which is not on the allowlist"
            )
        return pinned
    for candidate in ROUTE_MODEL_PREFERENCES.get(route.id, ()):
        if not allow_set or candidate in allow_set:
            return candidate
    fallback_id = fallback.strip()
    if fallback_id and (not allow_set or fallback_id in allow_set):
        return fallback_id
    if allow:
        return allow[0]
    raise RouterError("router has no model to choose")
