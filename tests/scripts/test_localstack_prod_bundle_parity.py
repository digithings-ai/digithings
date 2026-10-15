"""Every production supervisord program must have a local compose counterpart (DIG-3239).

`apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf` starts the
programs that make up the production container bundle. `docker-compose.yml` starts the
local equivalent. Nothing pinned the two together: the compose side had only point checks
(`test_compose_litellm_pinned.py`, `test_compose_searxng_sidecar.py`), so a program could
be added to production, or dropped from compose, with every existing test still green.

This guard asserts one direction — production -> local — and makes every gap explicit:

* a program that has no compose service is either an ALIAS (same thing, another name) or
  an EXCEPTION (deliberately absent, with the evidence that makes it deliberate);
* an EXCEPTION whose evidence stops being true fails here, so the exception cannot rot
  into a silent parity gap;
* EXCEPTIONS must equal the measured gap exactly, so an exception cannot be left behind
  after the counterpart appears.

Adding a 13th program to production therefore forces a decision here: add the local
counterpart, or record why not. That is the whole point of the ticket.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SUPERVISORD_CONF = (
    REPO_ROOT / "apps/digithings-stack-cloudflare/container/supervisor/supervisord.conf"
)
COMPOSE_FILE = REPO_ROOT / "docker-compose.yml"
SEED_CHROMA_SH = REPO_ROOT / "apps/digithings-stack-cloudflare/container/seed_chroma.sh"
SEED_SCRIPT = REPO_ROOT / "scripts/seed_digisearch_local.py"
ARCHITECTURE_MD = REPO_ROOT / "ARCHITECTURE.md"
MAKEFILE = REPO_ROOT / "Makefile"

# supervisord program name -> compose service running the same thing under another name.
# Each entry is only honest if the other name really resolves on the compose network, so
# test_litellm_alias_reaches_dns_name asserts the alias and the port it must answer on.
ALIASES = {"litellm": "digillm"}

# Programs with no compose service, and the evidence that makes the absence deliberate.
# A stale entry (the counterpart appeared, or the evidence moved) fails the exactness
# test below, so an exception cannot outlive its reason.
EXCEPTIONS = {
    "digigraph-mcp": (
        "loopback-only in production: served inside DigiStackContainer on :8766 with no "
        "public route (ARCHITECTURE.md, digigraph row), so it has no published port for "
        "compose to map"
    ),
    "seed_chroma": (
        "one-shot image-bake step, not a service: locally the same corpus is ingested by "
        "scripts/seed_digisearch_local.py (`make seed-digisearch-local`), and the script "
        "that seed_chroma runs honours DIGISEARCH_SEED_ROOT so both read the same root"
    ),
}


def _supervisord_programs() -> dict[str, str]:
    """Program name -> its whole config block, from every ``[program:NAME]`` section."""
    text = SUPERVISORD_CONF.read_text(encoding="utf-8")
    programs: dict[str, str] = {}
    for block in re.split(r"^\[", text, flags=re.MULTILINE):
        header = block.split("]", 1)[0]
        if not header.startswith("program:"):
            continue
        programs[header[len("program:") :].strip()] = block
    return programs


def _compose_services() -> dict:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))["services"]


def test_supervisord_programs_are_parsed() -> None:
    """The census the guard reasons about must be non-empty and must see known programs."""
    programs = _supervisord_programs()
    assert programs, f"no [program:*] sections parsed out of {SUPERVISORD_CONF}"
    for known in ("redis", "searxng", "digigraph", "litellm"):
        assert known in programs, (
            f"parser missed the known program {known!r}; it found {sorted(programs)} — "
            "the census below is measured by this parser, so a parsing fault reads as a "
            "parity result"
        )
    print(f"\nsupervisord programs: {len(programs)} -> {sorted(programs)}")
    print(f"compose services:    {len(_compose_services())}")


def test_every_supervisord_program_has_a_local_counterpart() -> None:
    programs = _supervisord_programs()
    services = _compose_services()
    missing = []
    for program in sorted(programs):
        if program in services or program in ALIASES or program in EXCEPTIONS:
            continue
        near = sorted(s for s in services if program in s or s in program)
        missing.append(f"{program} (closest compose service names: {near or 'none'})")
    assert not missing, (
        "supervisord programs with no local compose counterpart and no recorded "
        f"exception: {missing}. Add the service, add it to ALIASES, or record it in "
        "EXCEPTIONS with the evidence that makes the absence deliberate."
    )


def test_exception_table_is_exactly_the_measured_gap() -> None:
    """EXCEPTIONS must equal the programs with no counterpart — no more, no fewer."""
    programs = set(_supervisord_programs())
    services = set(_compose_services())
    gap = programs - services - set(ALIASES)
    assert gap == set(EXCEPTIONS), (
        f"EXCEPTIONS is stale: measured gap {sorted(gap)}, recorded {sorted(EXCEPTIONS)}. "
        "An exception must disappear the moment the local counterpart appears, and a new "
        "program without one must be recorded here with its reason."
    )


def test_digigraph_mcp_stays_documented_as_loopback_only() -> None:
    """The digigraph-mcp exception is only honest while the docs still say loopback-only."""
    lines = [
        line
        for line in ARCHITECTURE_MD.read_text(encoding="utf-8").splitlines()
        if "digigraph-mcp" in line
    ]
    documented = [line for line in lines if "loopback" in line.lower()]
    assert documented, (
        "no ARCHITECTURE.md line ties the digigraph-mcp supervisord program to loopback "
        f"any more; lines mentioning it: {lines or 'none'}. Update the doc with the new "
        "reachability, or re-justify the EXCEPTIONS entry."
    )
    # Control: the matcher must be able to miss, or this asserts nothing.
    assert [line for line in lines if "loopback" in line.lower() and "digivault" in line] == []


def test_seed_chroma_still_has_a_local_seed_path() -> None:
    """The seed_chroma exception stands only while a local seeding path exists and is wired."""
    assert SEED_SCRIPT.is_file(), (
        "scripts/seed_digisearch_local.py is gone: prod seeds the corpus in-image, and "
        "without this script the local stack has no counterpart at all — drop the "
        "EXCEPTIONS entry and fix the real gap"
    )
    makefile = MAKEFILE.read_text(encoding="utf-8")
    assert "seed-digisearch-local:" in makefile, (
        "the `seed-digisearch-local` Make target is gone, so the local seed path in "
        "EXCEPTIONS is no longer reachable"
    )
    assert "DIGISEARCH_SEED_ROOT" in makefile or "seed_digisearch_local.py" in makefile, (
        "the Makefile target must call scripts/seed_digisearch_local.py; otherwise the "
        "documented local counterpart is a different script"
    )
    seed_sh = SEED_CHROMA_SH.read_text(encoding="utf-8")
    assert "DIGISEARCH_SEED_ROOT" in seed_sh, (
        "seed_chroma.sh no longer honours DIGISEARCH_SEED_ROOT: it always reads the "
        "image-baked /seed, so local and prod cannot share a seed root and the "
        "EXCEPTIONS reason is no longer true"
    )


def test_litellm_alias_reaches_dns_name() -> None:
    """The litellm->digillm alias must be a name that resolves and a port that answers."""
    services = _compose_services()
    target = ALIASES["litellm"]
    assert target in services, (
        f"compose has no {target!r} service, so the litellm alias in ALIASES is dead"
    )
    aliases = services[target].get("networks", {}).get("default", {}).get("aliases", []) or []
    assert "litellm" in aliases, (
        f"{target!r} does not carry the network alias 'litellm' (aliases: {aliases}); "
        "anything resolving litellm by DNS in compose cannot reach it"
    )
    ports = [str(p) for p in services[target].get("ports", [])]
    assert any(p.endswith(":4000") for p in ports), (
        f"{target!r} publishes no :4000 (ports: {ports}), but the supervisord litellm "
        "program serves 4000 — the port parity the alias depends on is gone"
    )
