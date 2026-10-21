"""digillm's router: pick a model from the deployment allowlist.

Importing this package does not import the provider client. ``python -m
digillm.router`` does load the parent package, because that is how Python
runs a submodule.
"""

from digillm.router.decide import route_query
from digillm.router.policy import BUILTIN_ROUTES
from digillm.router.types import RouterDecision, RouterError, RouterRequest, RouterRoute

__all__ = [
    "BUILTIN_ROUTES",
    "RouterDecision",
    "RouterError",
    "RouterRequest",
    "RouterRoute",
    "route_query",
]
