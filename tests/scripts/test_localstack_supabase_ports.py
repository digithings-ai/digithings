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


def test_a_port_outside_the_range_does_not_become_one():
    """The repro: DT_SUPABASE_PORT=0 shifted the whole set by -55321."""
    for raw in ("0", "99999", "65536", "-1"):
        assert supabase_ports.api_port({"DT_SUPABASE_PORT": raw}) == (
            supabase_ports.DEFAULT_API_PORT
        ), raw


def test_a_port_that_would_shift_the_set_out_of_range_does_not_become_one():
    """1 puts the shadow port on 0; 65528 puts the pooler past 65535."""
    for raw in ("1", "65528", "65535"):
        assert supabase_ports.api_port({"DT_SUPABASE_PORT": raw}) == (
            supabase_ports.DEFAULT_API_PORT
        ), raw


def test_the_edges_of_the_usable_range_are_accepted():
    assert supabase_ports.api_port({"DT_SUPABASE_PORT": "2"}) == 2
    assert supabase_ports.api_port({"DT_SUPABASE_PORT": "65527"}) == 65527


def test_every_shifted_port_stays_inside_the_bindable_range():
    for value in (2, 54321, 55321, 65527):
        for name, port in supabase_ports.ports_for_api_port(value).items():
            assert supabase_ports.MIN_PORT <= port <= supabase_ports.MAX_PORT, (name, port)


def test_an_unusable_knob_never_writes_a_port_the_cli_cannot_bind():
    """The generated config.toml carried shadow_port = -1 and port = 0."""
    import re
    from pathlib import Path

    from scripts.localstack import supabase_flat

    config = Path(__file__).resolve().parents[2] / "digiquant" / "supabase" / "config.toml"
    text = config.read_text(encoding="utf-8")
    for raw in ("0", "99999", "1", "65528"):
        port_map = supabase_ports.ports_for_api_port(
            supabase_ports.api_port({"DT_SUPABASE_PORT": raw})
        )
        written = supabase_flat.rewrite_ports(text, port_map)
        assert "port = 0" not in written, raw
        assert "port = -1" not in written, raw
        for port in re.findall(r"\b(?:shadow_port|port)\s*=\s*(-?\d+)", written):
            assert supabase_ports.MIN_PORT <= int(port) <= supabase_ports.MAX_PORT, (raw, port)


def test_an_unusable_knob_is_reported(capsys):
    """A wrong knob has to say so, not only fall back."""
    supabase_ports.api_port({"DT_SUPABASE_PORT": "0"})
    err = capsys.readouterr().err
    assert "DT_SUPABASE_PORT" in err
    assert str(supabase_ports.DEFAULT_API_PORT) in err


def test_the_environment_carries_the_resolved_port(tmp_path):
    """The health gate reads the knob, so it has to read the resolved port."""
    from scripts.localstack import localenv

    env = {"DT_SUPABASE_PORT": "0"}
    localenv.apply_defaults(tmp_path, env)
    assert env["DT_SUPABASE_PORT"] == str(supabase_ports.DEFAULT_API_PORT)

    # a usable operator value still wins
    env = {"DT_SUPABASE_PORT": "55421"}
    localenv.apply_defaults(tmp_path, env)
    assert env["DT_SUPABASE_PORT"] == "55421"


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


def test_the_port_set_refuses_a_value_the_cli_cannot_bind():
    """The set is the last line of defence, and it was never reached.

    api_port resolves the knob first, so a test that only went through
    api_port never reached the guard inside the set: a caller handing it an
    unusable port - supabase_flat.py --api-port - would have written port 0
    and a negative shadow_port into the generated config.
    """
    canonical = supabase_ports.ports_for_api_port(supabase_ports.DEFAULT_API_PORT)
    for unusable in (0, -1, 99999, 65536):
        assert supabase_ports.ports_for_api_port(unusable) == canonical
    assert all(1 <= port <= 65535 for port in canonical.values())
