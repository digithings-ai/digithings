"""Public entry: one question in, one allowlisted model out."""

from __future__ import annotations

from digillm.router.classify import centroid_route, rule_route
from digillm.router.policy import bind_model, default_model, resolve_routes
from digillm.router.types import RouterDecision, RouterError, RouterRoute


def route_query(
    *,
    text: str,
    allowed: list[str],
    fallback: str,
    routes: list[RouterRoute] | None = None,
) -> RouterDecision:
    """Pick a model for ``text`` from ``allowed``.

    ``fallback`` is the deployment default (digichat's unconfigured default is
    deepseek-v4.1-flash-1017). It is used when the question has no strong
    signal, and it must itself be allowlisted when ``allowed`` is non-empty.
    """

    chosen_routes = resolve_routes(routes)
    if not chosen_routes:
        raise RouterError("router has no routes")
    bound = [(route, bind_model(route, allowed, fallback)) for route in chosen_routes]
    allow = [item.strip() for item in allowed if item.strip()]
    if len(allow) == 1:
        only = allow[0]
        route = next((item for item, model in bound if model == only), bound[0][0])
        return RouterDecision(
            route_id=route.id,
            label=route.label,
            model=only,
            reason="Only one model is on the allowlist.",
            confidence=1.0,
        )

    hit = rule_route(text, [route for route, _model in bound])
    if hit is None and text.strip():
        hit = centroid_route(text, [route for route, _model in bound])

    by_id = {route.id: (route, model) for route, model in bound}
    if hit is not None:
        route_id, reason, confidence = hit
        route, model = by_id[route_id]
        return _checked(route.id, route.label, model, reason, confidence, allow)

    model = default_model(allow, fallback)
    reason = (
        "Empty question — using the deployment default."
        if not text.strip()
        else "No strong signal — using the deployment default."
    )
    for route, bound_model in bound:
        if bound_model == model:
            return _checked(route.id, route.label, model, reason, 0.4, allow)
    return _checked("auto", "Auto", model, reason, 0.4, allow)


def _checked(
    route_id: str,
    label: str,
    model: str,
    reason: str,
    confidence: float,
    allow: list[str],
) -> RouterDecision:
    if allow and model not in allow:
        raise RouterError(f"router chose {model}, which is not on the allowlist")
    return RouterDecision(
        route_id=route_id,
        label=label,
        model=model,
        reason=reason,
        confidence=confidence,
    )
