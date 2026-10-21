"""Built-in categories and how they bind to a deployment's allowlist.

Auto on an unconfigured digichat install is ``deepseek/deepseek-v4.1-flash-1017``.
The router does not replace that default. It picks among Reasoning, Fast, and
Light. Reasoning and Fast walk a preference list until an id the deployment
allows. Light, unless an operator pins ``routes[].model``, is the cheapest
tool-capable non-Gemini model on that allowlist. An id that is not allowed is
never returned.
"""

from __future__ import annotations

from digillm.router.data import RouterCatalogModel, router_table
from digillm.router.types import RouterError, RouterRoute


def _preferences() -> dict[str, tuple[str, ...]]:
    return {route.id: tuple(route.prefer) for route in router_table().routes}


def _catalog() -> dict[str, RouterCatalogModel]:
    return {row.id: row for row in router_table().models}


def is_gemini(model_id: str) -> bool:
    """True when the last path segment starts with ``gemini``.

    ``google/gemini-3.1-flash-lite`` and a bare ``gemini-3.1-flash-lite`` are
    Gemini. ``google/gemma-4-31b-it`` is not.
    """

    segment = model_id.strip().rsplit("/", 1)[-1].lower()
    return segment.startswith("gemini")


BUILTIN_ROUTES: tuple[RouterRoute, ...] = tuple(
    RouterRoute(
        id=route.id,
        label=route.label,
        description=route.description,
        exemplars=list(route.exemplars),
    )
    for route in router_table().routes
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


def _priced(model_id: str) -> float | None:
    row = _catalog().get(model_id)
    if row is None or row.tool_call is not True:
        return None
    price = row.prompt_usd_per_million
    if isinstance(price, bool) or not isinstance(price, int | float):
        return None
    return float(price)


def _cheapest_light(allow: list[str], fallback: str) -> str | None:
    """Cheapest tool-capable non-Gemini id on ``allow``.

    A non-empty allowlist walks priced rows first (lower prompt price, then
    earlier in the allowlist). Unpriced ids, including the deployment default
    when the catalog has no row, cannot win that walk. With no priced
    candidate, the first non-Gemini id wins. An allowlist that is only Gemini
    uses the fallback when it is on the list, otherwise the first id.

    An empty allowlist is "no restriction". Light stays on the deployment
    fallback when that id is not Gemini, so an unconfigured container does not
    jump to the globally cheapest catalog row.
    """

    if allow:
        priced = [
            (price, index, model_id)
            for index, model_id in enumerate(allow)
            if not is_gemini(model_id) and (price := _priced(model_id)) is not None
        ]
        if priced:
            priced.sort()
            return priced[0][2]
        for model_id in allow:
            if not is_gemini(model_id):
                return model_id
        fallback_id = fallback.strip()
        if fallback_id and fallback_id in set(allow):
            return fallback_id
        return allow[0]
    fallback_id = fallback.strip()
    if fallback_id and not is_gemini(fallback_id):
        return fallback_id
    return None


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
    if route.id == "light" and router_table().light_select == "cheapest_tool_capable_non_gemini":
        chosen = _cheapest_light(allow, fallback)
        if chosen is not None:
            return chosen
    for candidate in _preferences().get(route.id, ()):
        if not allow_set or candidate in allow_set:
            return candidate
    fallback_id = fallback.strip()
    if fallback_id and (not allow_set or fallback_id in allow_set):
        return fallback_id
    if allow:
        return allow[0]
    raise RouterError("router has no model to choose")
