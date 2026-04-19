"""Shared environment-variable substitution helper for DigiGraph.

Resolves ``${VAR}`` and ``${VAR:-default}`` references in strings and arbitrarily
nested dicts/lists.

Behaviour on a missing variable (no default):
- ``errors`` is ``None`` (silent mode, used by ``project_config``): returns ``""``
- ``errors`` is a list (tracked mode, used by ``project_validate``): preserves the
  original ``${VAR}`` literal and appends a human-readable message to ``errors``.
"""

from __future__ import annotations

import os
import re
from typing import Any

# Matches ${VAR} or ${VAR:-default}.  VAR must be a valid env-var identifier.
_ENV_REF = re.compile(r"\$\{([A-Za-z_][A-Za-z0-9_]*)(?::-([^}]*))?\}")


def resolve_env_refs(
    value: Any,
    *,
    env: dict[str, str] | None = None,
    errors: list[str] | None = None,
    path: str = "$",
) -> Any:
    """Walk *value* substituting ``${VAR}`` / ``${VAR:-default}`` in strings.

    Parameters
    ----------
    value:
        A string, dict, list, or any other type.  Non-string scalars are returned
        unchanged.
    env:
        Mapping of environment variables.  Defaults to ``os.environ``.
    errors:
        When provided (tracked mode), unresolved references (no default, not set)
        cause the original ``${VAR}`` to be preserved in the output and an error
        message to be appended here.  When ``None`` (silent mode), unresolved
        references are replaced with ``""``.
    path:
        JSONPath-style string used in error messages when *errors* is provided.

    Returns
    -------
    Any
        The same type as *value* with all env refs resolved.
    """
    _env = os.environ if env is None else env

    if isinstance(value, str):

        def _sub(match: re.Match[str]) -> str:
            var = match.group(1)
            default = match.group(2)
            if var in _env:
                return _env[var]
            if default is not None:
                return default
            # Variable is missing and has no default.
            if errors is not None:
                errors.append(
                    f"{path}: unresolved environment variable '${{{var}}}' "
                    "(no default and not set in environment)"
                )
                return match.group(0)  # preserve literal in tracked mode
            return ""  # silent mode

        return _ENV_REF.sub(_sub, value)

    if isinstance(value, dict):
        return {
            k: resolve_env_refs(v, env=_env, errors=errors, path=f"{path}.{k}")
            for k, v in value.items()
        }
    if isinstance(value, list):
        return [
            resolve_env_refs(v, env=_env, errors=errors, path=f"{path}[{i}]")
            for i, v in enumerate(value)
        ]
    return value
