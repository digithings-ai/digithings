"""The local stack's Supabase port knob (DIG-4501).

core-local already holds 54321-54324, so the digithings local stack has to run
on another port set. The Supabase CLI 2.117.0 has no port flags, so the ports
live in the generated config.toml; this module is the one place that knows
them, and the CLI reads the result.
"""

from __future__ import annotations

import pytest

from scripts.localstack import supabase_ports

pytestmark = pytest.mark.unit


def test_the_default_port_set_clears_core_local():
    """The default has to move the whole set, or the local stack cannot come up."""
    assert supabase_ports.DEFAULT_API_PORT != supabase_ports.CANONICAL_API_PORT
    ports = supabase_ports.ports({})
    for name, canonical in supabase_ports.CANONICAL_PORTS.items():
        assert ports[name] != canonical, name


def test_the_knob_shifts_the_whole_set_by_one_delta():
    ports = supabase_ports.ports_for_api_port(55321)
    assert ports["api"] == 55321
    assert ports["db"] == 55322
    assert ports["shadow"] == 55320
    assert ports["pooler"] == 55329
    assert ports["studio"] == 55323
    assert ports["inbucket"] == 55324
    assert ports["analytics"] == 55327


def test_every_port_line_in_the_checked_in_config_is_mapped():
    """A port the map does not know is a port the CLI still tries to bind.

    The [analytics] port was missed once and the stack died with
    "Bind for 0.0.0.0:54327 failed: port is already allocated".
    """
    import re
    from pathlib import Path

    config = Path(__file__).resolve().parents[2] / "digiquant" / "supabase" / "config.toml"
    table = None
    found = set()
    for line in config.read_text(encoding="utf-8").splitlines():
        head = re.match(r"^\s*\[([^\]]+)\]\s*$", line)
        if head:
            table = head.group(1)
            continue
        key = re.match(r"^\s*(port|shadow_port)\s*=\s*(\d+)", line)
        if key and table:
            found.add((table, key.group(1)))
    assert found, "no port lines found in the checked-in config.toml: the scan is void"
    mapped = set(supabase_ports.PORT_KEYS.values())
    for pair in sorted(found):
        assert pair in mapped, f"unmapped port {pair} in the checked-in config.toml"


def test_the_knob_is_read_from_the_environment():
    assert supabase_ports.api_port({"DT_SUPABASE_PORT": "55421"}) == 55421
    assert supabase_ports.api_port({}) == supabase_ports.DEFAULT_API_PORT
    # a value that is not a port does not become one
    assert supabase_ports.api_port({"DT_SUPABASE_PORT": "not-a-port"}) == (
        supabase_ports.DEFAULT_API_PORT
    )


def test_every_port_names_the_table_and_the_key_it_rewrites():
    for name, (table, key) in supabase_ports.PORT_KEYS.items():
        assert name in supabase_ports.CANONICAL_PORTS
        assert table and key


def test_the_checked_in_config_toml_still_carries_the_canonical_ports():
    """The checked-in file is the template; only the generated copy moves."""
    from pathlib import Path

    config = Path(__file__).resolve().parents[2] / "digiquant" / "supabase" / "config.toml"
    text = config.read_text(encoding="utf-8")
    assert f"port = {supabase_ports.CANONICAL_PORTS['api']}" in text
    assert f"port = {supabase_ports.CANONICAL_PORTS['db']}" in text
