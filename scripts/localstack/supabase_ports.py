"""The local stack's Supabase port map.

core-local already holds the Supabase default ports (54321-54324), so the
digithings local stack needs a port set of its own. The Supabase CLI (2.117.0)
has no port flags, so the ports live in the generated ``config.toml``; this
module is the one place that knows them, and the health gate reads the same
knob.

One knob: ``DT_SUPABASE_PORT`` is the Supabase API port. Every other port
moves with it by the same delta, so a stack never straddles two port sets.

A knob value that cannot carry the whole set never becomes one: the ports
have to be bindable, so the default port set is used instead and the refusal
is printed. A half-shifted set is a config the CLI cannot bind -- with the
API port on 0 the shadow port lands on -1.
"""
from __future__ import annotations

import os
import sys
from typing import Dict, Mapping, Optional, Tuple

#: The environment variable that carries the port knob.
PORT_ENV = "DT_SUPABASE_PORT"

#: The API port in the checked-in digiquant/supabase/config.toml.
CANONICAL_API_PORT = 54321

#: The API port the local stack uses by default. core-local holds the
#: canonical set, so the default is already a different one.
DEFAULT_API_PORT = 55321

#: The lowest port the local stack may use.
MIN_PORT = 1

#: The highest port the local stack may use.
MAX_PORT = 65535

#: The checked-in config.toml port values, by name.
CANONICAL_PORTS: Dict[str, int] = {
    "api": 54321,
    "db": 54322,
    "shadow": 54320,
    "pooler": 54329,
    "studio": 54323,
    "inbucket": 54324,
    "analytics": 54327,
}

#: The config.toml table and key each port lives under.
PORT_KEYS: Dict[str, Tuple[str, str]] = {
    "api": ("api", "port"),
    "db": ("db", "port"),
    "shadow": ("db", "shadow_port"),
    "pooler": ("db.pooler", "port"),
    "studio": ("studio", "port"),
    "inbucket": ("inbucket", "port"),
    "analytics": ("analytics", "port"),
}


def _shifted(value: int) -> Dict[str, int]:
    """The canonical port set, moved by the delta one API port implies."""
    delta = int(value) - CANONICAL_API_PORT
    return {name: port + delta for name, port in CANONICAL_PORTS.items()}


def _unusable(value: int, shifted: Mapping[str, int]) -> Optional[str]:
    """Why this API port cannot carry the port set, or ``None`` when it can."""
    if not MIN_PORT <= value <= MAX_PORT:
        return f"{value} is outside {MIN_PORT}-{MAX_PORT}"
    outside = sorted(name for name, port in shifted.items() if not MIN_PORT <= port <= MAX_PORT)
    if outside:
        return (
            f"{value} would put the Supabase set outside {MIN_PORT}-{MAX_PORT} "
            f"({', '.join(outside)})"
        )
    return None


def _report(problem: str) -> None:
    """Say what was refused and which port is used instead."""
    print(
        f"supabase-ports: {PORT_ENV} {problem}; using {DEFAULT_API_PORT} instead",
        file=sys.stderr,
    )


def api_port(env: Optional[Mapping[str, str]] = None) -> int:
    """The Supabase API port the local stack uses.

    A knob that cannot carry the whole port set never becomes one: the
    default port is used instead, and the refusal is printed.
    """
    env = os.environ if env is None else env
    raw = str(env.get(PORT_ENV) or "").strip()
    if raw.isascii() and raw.isdigit():
        value = int(raw)
        problem = _unusable(value, _shifted(value))
        if problem is None:
            return value
        _report(problem)
        return DEFAULT_API_PORT
    if raw:
        _report(f"{raw!r} is not a port")
    return DEFAULT_API_PORT


def ports_for_api_port(value: int) -> Dict[str, int]:
    """Every Supabase port for an API port, shifted by one delta.

    A value that cannot carry the whole set is refused and the default set
    is used instead, so no caller can write a config carrying a port the
    CLI cannot bind.
    """
    try:
        value = int(value)
    except (TypeError, ValueError):
        _report(f"{value!r} is not a port")
        value = DEFAULT_API_PORT
    shifted = _shifted(value)
    problem = _unusable(value, shifted)
    if problem is not None:
        _report(problem)
        shifted = _shifted(DEFAULT_API_PORT)
    return shifted


def ports(env: Optional[Mapping[str, str]] = None) -> Dict[str, int]:
    """Every Supabase port the local stack uses."""
    return ports_for_api_port(api_port(env))
