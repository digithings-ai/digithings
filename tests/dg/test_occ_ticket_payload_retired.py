"""DIG-1380 Act A: the committed occ_tickets PII snapshot is retired from the tip.

Board approval ``e4c1d067``. ``container/seed/occ_tickets.jsonl`` was a committed
Zammad export carrying 323 customer email addresses plus 372 ``[internal]`` staff
notes, and ``container/seed_chroma.sh`` re-ingested it into the tenant corpus on
every cold boot. This module is the executable statement of the containment:

* the snapshot is not in the tree, and nothing re-ingests it;
* no tenant corpus map still routes to the retired index;
* no deployed prompt still advertises that index or the PII it carried.

The three corpus-map blobs are deliberately asserted together rather than one at
a time: ``scripts/check_tenant_corpus_map.py`` fails the moment they disagree,
so a partial trim is not a passing state. ``226ecc0ac`` (fan-out leg isolation)
stays in place; with it, dropping a leg cannot deny the surviving leg.
"""

from __future__ import annotations

import json
import subprocess
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]

#: The blobs ``scripts/check_tenant_corpus_map.py`` compares. The compose
#: override is the one that has bitten this tree before: trimming only wrangler
#: and index.ts leaves the drift gate red.
COMPOSE_BLOB = REPO_ROOT / "infra/digichat-release/compose.profile-a-bundle.override.yml"
WRANGLER_BLOB = REPO_ROOT / "apps/digithings-stack-cloudflare/wrangler.toml"
INDEX_TS_BLOB = REPO_ROOT / "apps/digithings-stack-cloudflare/src/index.ts"

#: Operator-facing copies of the same fan-out. Not compared by the drift gate,
#: so nothing else fails if they go stale - which is exactly why they are pinned
#: here instead.
ENV_EXAMPLE_BLOB = REPO_ROOT / "infra/digichat-release/.env.profile-a-bundle.example"
OCC_EMBED_YAML = REPO_ROOT / "apps/digichat/config/examples/occ-embed.yaml"
DIGICHAT_SCHEMA_TEST = REPO_ROOT / "apps/digichat/src/lib/deploy-config/schema.test.ts"

SEED_SCRIPT = REPO_ROOT / "apps/digithings-stack-cloudflare/container/seed_chroma.sh"
TICKET_SNAPSHOT = REPO_ROOT / "apps/digithings-stack-cloudflare/container/seed/occ_tickets.jsonl"
SEED_DIR = REPO_ROOT / "apps/digithings-stack-cloudflare/container/seed"

#: Every blob that embeds the OCC tenant map, in one tuple so the retirement
#: assertion below cannot be satisfied by fixing only some of them.
MAP_BLOBS = (
    pytest.param(COMPOSE_BLOB, id="compose-override"),
    pytest.param(WRANGLER_BLOB, id="wrangler-toml"),
    pytest.param(INDEX_TS_BLOB, id="index-ts-fallback"),
    pytest.param(ENV_EXAMPLE_BLOB, id="env-example"),
    pytest.param(OCC_EMBED_YAML, id="occ-embed-yaml"),
)

#: Strings that assert the corpus holds live customer PII. Any of these surviving
#: in a deployed prompt means the model was told to quote real ticket content.
PII_ADVERTISEMENTS = (
    "full customer names/emails",
    "internal notes tagged [internal]",
    "internal ticket notes are included",
    "customer names and emails are shown in full",
    "[internal]",
)

#: The ticket-grounding recipe block. The zammad tool names stay in the tree on
#: the live MCP route (Act B, tracked separately); what must not survive here is
#: the prompt promising grounding that the retired index used to provide.
RECIPE_MARKERS = (
    "occ_tickets",
    "Ticket content lives in TWO places",
    "zammad_aggregate_tickets",
    "zammad_search_tickets",
    "zammad_get_ticket",
    "zammad_ticket_report",
    "fan-out",
)


def _text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _compose_corpus_map() -> dict:
    """Read from ``digithings-stack``, not ``digichat``: in this override the
    stack service is the one that consumes DIGI_TENANT_CORPUS_MAP, and that is
    also where the prompt ships in compose."""
    return json.loads(_compose_env()["DIGI_TENANT_CORPUS_MAP"])["occ"]


def _compose_env() -> dict:
    """Environment of both compose services merged. Each carries exactly one of
    the two maps, so the union is unambiguous."""
    services = yaml.safe_load(_text(COMPOSE_BLOB))["services"]
    env = dict(services["digichat"]["environment"])
    env.update(services["digithings-stack"]["environment"])
    return env


def _compose_embed_backend() -> dict:
    return json.loads(_compose_env()["DIGICHAT_EMBED_TENANTS"])["occ.digithings.ai"]["backend"]


def _occ_map_from_wrangler() -> dict:
    raw = tomllib.loads(_text(WRANGLER_BLOB))["vars"]["DIGI_TENANT_CORPUS_MAP"]
    return json.loads(raw)["occ"]


def _index_ts_corpus_map() -> dict:
    """The hardcoded fallback literal. Whitespace between ``??`` and the quote
    has moved around between commits, so anchor on the variable name and take the
    first following line that carries a quoted string."""
    source = _text(INDEX_TS_BLOB)
    after = source[source.index("DIGI_TENANT_CORPUS_MAP") :].splitlines()
    line = next(ln for ln in after if "'" in ln)
    literal = line[line.index("'") + 1 : line.rindex("'")]
    return json.loads(_unjs(literal))["occ"]


def _unjs(literal: str) -> str:
    """Resolve the escapes of a single-quoted JS string literal into raw JSON."""
    for src, dst in (("\\\\", "\x00"), ("\\'", "'"), ('\\"', '"'), ("\\n", "\n"), ("\\t", "\t")):
        literal = literal.replace(src, dst)
    return literal.replace("\x00", "\\")


def _prompts() -> list[tuple[str, str]]:
    return [
        ("compose-override", _compose_corpus_map()["researchSystemPrompt"]),
        ("wrangler-toml", _occ_map_from_wrangler()["researchSystemPrompt"]),
        ("index-ts-fallback", _index_ts_corpus_map()["researchSystemPrompt"]),
    ]


# --- payload at rest -------------------------------------------------------


def test_ticket_snapshot_is_not_in_the_tree() -> None:
    assert not TICKET_SNAPSHOT.exists(), (
        "the committed Zammad snapshot still carries customer emails and [internal] "
        "notes; it must not be in the tip"
    )


def test_seed_dir_carries_no_jsonl_payload() -> None:
    leaked = sorted(p.relative_to(REPO_ROOT).as_posix() for p in SEED_DIR.rglob("*.jsonl"))
    assert leaked == [], f"unexpected JSONL payload(s) in the container seed dir: {leaked}"


def test_seed_script_does_not_reingest_tickets() -> None:
    source = _text(SEED_SCRIPT)
    assert "seed_tickets" not in source, "seed_chroma.sh still defines or calls seed_tickets"
    assert "occ_tickets.jsonl" not in source, "seed_chroma.sh still points at the retired payload"


def test_seed_script_is_valid_shell() -> None:
    subprocess.run(["sh", "-n", str(SEED_SCRIPT)], check=True)


# --- fan-out ---------------------------------------------------------------


@pytest.mark.parametrize("blob", MAP_BLOBS)
def test_no_tenant_blob_routes_to_the_retired_index(blob: Path) -> None:
    assert "occ_tickets" not in _text(blob), f"{blob.name} still routes to the retired index"


def test_compose_embed_tenant_index_is_occ_help_only() -> None:
    """The copy ``scripts/check_tenant_corpus_map.py`` reads. The other compose
    copy is asserted separately, and for good reason."""
    assert _compose_embed_backend()["digisearchIndex"] == "occ_help"


def test_compose_corpus_map_index_is_occ_help_only() -> None:
    """The compose override carries the map twice: once inside
    ``DIGICHAT_EMBED_TENANTS`` (what the drift gate compares) and once in its own
    ``DIGI_TENANT_CORPUS_MAP`` (which carries the prompt and is compared by
    nothing). Trimming only the first leaves the second advertising the index."""
    assert _compose_corpus_map()["digisearchIndex"] == "occ_help"


def test_wrangler_occ_index_is_occ_help_only() -> None:
    assert _occ_map_from_wrangler()["digisearchIndex"] == "occ_help"


def test_index_ts_fallback_occ_index_is_occ_help_only() -> None:
    assert _index_ts_corpus_map()["digisearchIndex"] == "occ_help"


def test_occ_tenant_keeps_its_vault_prefix() -> None:
    """Trimming the fan-out leg must not disturb the rest of the tenant entry."""
    prefix = "clients/online-compliance-center"
    assert _compose_embed_backend()["vaultPathPrefix"] == prefix
    assert _compose_corpus_map()["vaultPathPrefix"] == prefix
    assert _occ_map_from_wrangler()["vaultPathPrefix"] == prefix
    assert _index_ts_corpus_map()["vaultPathPrefix"] == prefix


def test_corpus_map_drift_gate_passes() -> None:
    result = subprocess.run(
        ["python3", "scripts/check_tenant_corpus_map.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
    )
    assert result.returncode == 0, result.stdout + result.stderr


# --- deployed prompt -------------------------------------------------------


@pytest.mark.parametrize("blob", MAP_BLOBS)
def test_no_blob_embeds_the_retired_index(blob: Path) -> None:
    assert "occ_tickets" not in _text(blob)


@pytest.mark.parametrize(("blob", "prompt"), _prompts())
def test_prompt_stops_advertising_customer_pii(blob: str, prompt: str) -> None:
    assert prompt, f"{blob} lost its researchSystemPrompt entirely"
    for phrase in PII_ADVERTISEMENTS:
        assert phrase not in prompt, f"{blob} prompt still advertises {phrase!r}"


@pytest.mark.parametrize(("blob", "prompt"), _prompts())
def test_prompt_drops_ticket_grounding_recipes(blob: str, prompt: str) -> None:
    for marker in RECIPE_MARKERS:
        assert marker not in prompt, f"{blob} prompt still references {marker!r}"


@pytest.mark.parametrize(("blob", "prompt"), _prompts())
def test_prompt_still_grounds_answers_in_occ_help(blob: str, prompt: str) -> None:
    """Removing the leak must not leave OCC without its grounding instruction."""
    assert "occ_help" in prompt, f"{blob} prompt no longer names the surviving index"
    assert "digivault_search_notes" in prompt


# --- operator-facing copies ------------------------------------------------


def test_env_example_occ_index_is_occ_help_only() -> None:
    source = _text(ENV_EXAMPLE_BLOB)
    assert "occ_help,occ_tickets" not in source
    assert '"digisearchIndex":"occ_help"' in source


def test_occ_embed_example_uses_occ_help_only() -> None:
    config = yaml.safe_load(_text(OCC_EMBED_YAML))
    assert config["hosts"]["occ.digithings.ai"]["backend"]["digisearchIndex"] == "occ_help"


def test_digichat_schema_test_expectation_matches_the_example() -> None:
    assert '"occ_help,occ_tickets"' not in _text(DIGICHAT_SCHEMA_TEST)