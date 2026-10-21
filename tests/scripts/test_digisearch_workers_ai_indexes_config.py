"""DIG-4657: the bge-m3 index list must reach the digisearch container.

PR #5937 shipped the per-index override in ``digisearch/src/digisearch/search/_stub.py``
(``_workers_ai_indexes`` / ``_embedding_provider_for``): the indexes named by
``DIGISEARCH_WORKERS_AI_INDEXES`` are queried with Cloudflare Workers AI
``@cf/baai/bge-m3`` (1024 dims); every other index keeps the configured default
provider (384 dims).

The override landed without the configuration path that feeds it. The var was in no
``wrangler.toml`` [vars], in no container ``envVars`` and in no contract row, so the
list was always empty. Every index was then queried with the 384-dim default provider --
including the indexes the corpus-index worker writes with bge-m3 (1024 dims). A 384-dim
query vector against a 1024-dim index matches nothing, and Vectorize's rejection is
silent at the query level: the corpus looks empty rather than broken.

These checks pin the configuration path end to end -- the shipped value, the contract
row that declares it, the container passthrough, and the digisearch code that acts on
it -- so the list cannot go back to being empty without a test failing.
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
STACK = REPO_ROOT / "apps" / "digithings-stack-cloudflare"
WRANGLER = STACK / "wrangler.toml"
INDEX_TS = STACK / "src" / "index.ts"
CONTRACT = REPO_ROOT / "config" / "contract" / "contract.yaml"

VAR = "DIGISEARCH_WORKERS_AI_INDEXES"

#: The index-name rule the corpus-index worker enforces on the Vectorize indexes it
#: writes (``apps/corpus-index/src/config.ts``: ``const INDEX = /^[a-z0-9][a-z0-9-]{0,62}$/``).
#: Dash form, no underscore. The 384-dim indexes the default provider writes are
#: underscore form, so a listed index can never be one of them: listing one would put
#: a 384-dim query in front of an index that holds 384-dim vectors written with the
#: default provider, and silently break that corpus.
CORPUS_INDEX_NAME_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")


def _wrangler_vars() -> dict[str, str]:
    return tomllib.loads(WRANGLER.read_text(encoding="utf-8"))["vars"]


def _contract_row(name: str) -> dict | None:
    contract = yaml.safe_load(CONTRACT.read_text(encoding="utf-8"))
    for row in contract["env"]:
        if row["name"] == name:
            return row
    return None


def _shipped_value() -> str:
    """The var as the Worker ships it ("" when it is not set at all)."""
    return _wrangler_vars().get(VAR, "")


def _shipped_list() -> list[str]:
    return [part.strip() for part in _shipped_value().split(",") if part.strip()]


def test_worker_ships_a_non_empty_index_list() -> None:
    """An unset (or empty) var is the exact failure this ticket is about."""
    value = _shipped_value()
    assert value, (
        f"{VAR} is not set in {WRANGLER.relative_to(REPO_ROOT)} [vars]. The per-index "
        "bge-m3 override in digisearch (search/_stub.py) reads this var, so without it "
        "every index is queried with the 384-dim default provider -- including the "
        "indexes the corpus-index worker writes with bge-m3 (1024 dims), which then "
        "match nothing."
    )
    assert value.strip() == value, f"{VAR} carries stray whitespace: {value!r}"
    assert _shipped_list(), f"{VAR}={value!r} parses to an empty index list"


def test_contract_declares_the_var_with_the_shipped_value() -> None:
    """The contract is where the deployment's environment is declared."""
    row = _contract_row(VAR)
    assert row is not None, (
        f"{VAR} has no row in {CONTRACT.relative_to(REPO_ROOT)}. Every wrangler [vars] "
        "name must be declared there (config/contract/check_contract.py)."
    )
    assert row.get("secret") is False, f"{VAR} is a plain var, not a secret"
    assert "digithings-stack" in row["sources"]["wrangler_workers"], (
        f"{VAR} is shipped by the stack worker, so the contract must name it as a source: "
        f"{row['sources']['wrangler_workers']}"
    )
    assert row["wrangler_values"]["digithings-stack"] == _shipped_value(), (
        "the contract transcribes the live wrangler.toml value; a stale transcription "
        "hides the shipped value from the contract check (DIG-3232)"
    )


def test_container_forwards_the_var_to_digisearch() -> None:
    """The stack forwards an explicit env whitelist; a var outside it never reaches
    the digisearch process, however it is set on the Worker."""
    source = INDEX_TS.read_text(encoding="utf-8")
    assert f'{VAR}: env.{VAR} ?? ""' in source, (
        f"{VAR} is not forwarded to the container in {INDEX_TS.relative_to(REPO_ROOT)}. "
        "src/index.ts forwards an explicit envVars whitelist, so a Worker var that is "
        "not in it does not reach the digisearch process at all."
    )
    assert re.search(rf"^\s*{VAR}\?: string;$", source, re.MULTILINE), (
        f"{VAR} is missing from the Env interface in "
        f"{INDEX_TS.relative_to(REPO_ROOT)}"
    )


def test_digisearch_acts_on_the_shipped_list(monkeypatch) -> None:
    """The shipped value must be the value digisearch reads and acts on."""
    from digisearch.embedding.providers.workers_ai import WorkersAiEmbedder
    from digisearch.search._stub import _embedding_provider_for, _workers_ai_indexes

    monkeypatch.setenv(VAR, _shipped_value())
    monkeypatch.delenv("DIGISEARCH_BGE_M3_EMBED_URL", raising=False)
    monkeypatch.delenv("DIGISEARCH_BGE_M3_EMBED_TOKEN", raising=False)

    assert _workers_ai_indexes() == frozenset(_shipped_list()), (
        "digisearch did not parse the shipped list into the set it queries with"
    )
    for index in _shipped_list():
        provider = _embedding_provider_for(index, "acct", "vtok")
        assert isinstance(provider, WorkersAiEmbedder), (
            f"{index} is listed in {VAR} but digisearch still queries it with the "
            "default provider, so the query vector does not match the bge-m3 vectors "
            "the corpus-index worker wrote"
        )


def test_every_listed_index_is_a_corpus_index_name() -> None:
    """A listed index must be one the corpus-index worker can write."""
    for index in _shipped_list():
        assert CORPUS_INDEX_NAME_RE.match(index), (
            f"{index!r} is listed in {VAR} but is not a valid corpus-index index name "
            "(dash form, lowercase, at most 63 chars). An index the corpus-index "
            "worker cannot write is never written with bge-m3, so listing it would "
            "break the corpus it names."
        )


def test_the_list_names_the_bge_m3_ticket_corpus() -> None:
    """The shipped list is the ticket corpus the corpus-index worker writes with bge-m3.

    The authoritative source for the index names is the corpus-index job record in KV
    (``corpus-index:jobs``), which is not in this repo. The value below is the one the
    original DIG-3269 wiring shipped; if the live job record names a different ticket
    index, this pin moves with it.
    """
    assert _shipped_list() == ["occ-tickets"], (
        f"{VAR} ships {_shipped_list()!r}. The bge-m3 ticket corpus index is "
        "'occ-tickets' (the value the original DIG-3269 wiring shipped). Update this "
        "pin together with the corpus-index job record if that name changes."
    )
