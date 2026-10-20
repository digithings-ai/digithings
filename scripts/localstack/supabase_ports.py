"""The local stack's Supabase port map.

core-local already holds the Supabase default ports (54321-54324), so the
digithings local stack needs a port set of its own. The Supabase CLI (2.117.0)
has no port flags, so the ports live in the generated ``config.toml``; this
module is the one place that knows them, and the health gate reads the same
knob.

One knob: ``DT_SUPABASE_PORT`` is the Supabase API port. Every other port
moves with it by the same delta, so a stack never straddles two port sets.
"""
from __future__ import annotations

import os
from typing import Dict, Mapping, Optional, Tuple

#: The environment variable that carries the port knob.
PORT_ENV = "DT_SUPABASE_PORT"

#: The API port in the checked-in digiquant/supabase/config.toml.
CANONICAL_API_PORT = 54321

#: The API port the local stack uses by default. core-local holds the
#: canonical set, so the default is already a different one.
DEFAULT_API_PORT = 55321

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


def api_port(env: Optional[Mapping[str, str]] = None) -> int:
    """The Supabase API port the local stack uses."""
    env = os.environ if env is None else env
    raw = str(env.get(PORT_ENV) or "").strip()
    if raw.isdigit():
        return int(raw)
    return DEFAULT_API_PORT


def ports_for_api_port(value: int) -> Dict[str, int]:
    """Every Supabase port for an API port, shifted by one delta."""
    delta = int(value) - CANONICAL_API_PORT
    return {name: port + delta for name, port in CANONICAL_PORTS.items()}


def ports(env: Optional[Mapping[str, str]] = None) -> Dict[str, int]:
    """Every Supabase port the local stack uses."""
    return ports_for_api_port(api_port(env))
