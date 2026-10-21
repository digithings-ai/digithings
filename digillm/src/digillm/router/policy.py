"""Built-in categories and how they bind to a deployment's allowlist.

Each category calls the model ``model_catalog.json`` resolves for that
preset (Reasoning, Fast, Light). Auto is the pinned catalog model and the
fallback when that preset is not on the allowlist. An operator pin
(``routes[].model``) wins. An id that is not allowed is never returned.
Prices stay in the catalog. They are not walked.
"""

from __future__ import annotations

from digillm.router.catalog import premium_ids, preset_ids
from digillm.router.data import router_table
from digillm.router.types import RouterError, RouterRoute


def _preset_model(route_id: str) -> str:
    return preset_ids().get(route_id, "")


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


def _allowed(model_id: str, allow_set: set[str]) -> bool:
    return bool(model_id) and (not allow_set or model_id in allow_set)


def default_model(allowed: list[str], fallback: str) -> str:
    """Auto when the deployment allows it, otherwise the caller's fallback."""

    allow = [item.strip() for item in allowed if item.strip()]
    allow_set = set(allow)
    auto = preset_ids()["auto"].strip()
    if _allowed(auto, allow_set):
        return auto
    fallback_id = fallback.strip()
    if _allowed(fallback_id, allow_set):
        return fallback_id
    if allow:
        return allow[0]
    raise RouterError("router has no model to choose")


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
        if pinned in premium_ids():
            raise RouterError(f"router will not use premium model {pinned}")
        if allow_set and pinned not in allow_set:
            raise RouterError(
                f"router route {route.id} pins {pinned}, which is not on the allowlist"
            )
        return pinned
    preset = _preset_model(route.id).strip()
    if _allowed(preset, allow_set):
        return preset
    auto = preset_ids()["auto"].strip()
    if _allowed(auto, allow_set):
        return auto
    fallback_id = fallback.strip()
    if _allowed(fallback_id, allow_set):
        return fallback_id
    if allow:
        return allow[0]
    raise RouterError("router has no model to choose")
