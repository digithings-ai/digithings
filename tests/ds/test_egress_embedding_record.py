"""Egress records on the remote OpenAI embedding path (DIG-1141, Leaf C).

``digisearch`` reaches a model provider on a path that never enters
``digillm``: ``OpenAIEmbedder`` drives ``openai.OpenAI`` itself. A record emitted
only inside ``digillm.client`` therefore cannot see it, so "every outbound model
call leaves a record" was false until this leaf. What is pinned here:

* one remote ``embed()`` call emits exactly one record, carrying the resolved
  destination, the model, the decision, the category ids and a keyed digest;
* the local MiniLM path emits nothing, builds no OpenAI client, and reads none of
  the remote configuration;
* no record ever carries the input texts;
* a missing or unusable pepper yields ``absent`` and no hash of any kind.

The last group is not padding. It is what makes the lazy ``digillm`` import in the
provider honest: the tests cannot build the deployed image, so they pin the two
declarations the argument rests on (digillm and openai in one extra, the image not
installing that extra) and the absence of a second digest implementation. Without
those, a green run here proves only that the repository's ``pytest.ini`` happens
to put ``digillm/src`` on ``pythonpath``.
"""

from __future__ import annotations

import os
import re
import sys
import tomllib
from collections.abc import Iterator, MutableMapping
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import digisearch.embedding.providers.minilm as minilm_module
import pytest
from digillm.telemetry import CallPurpose
from digisearch.embedding.providers.openai import OpenAIEmbedder

from digillm import egress_record as egress

pytestmark = pytest.mark.unit

_REPO_ROOT = Path(__file__).resolve().parents[2]
_PROVIDER_SOURCE = _REPO_ROOT / "digisearch/src/digisearch/embedding/providers/openai.py"
_PYPROJECT = _REPO_ROOT / "digisearch/pyproject.toml"
_DOCKERFILE = _REPO_ROOT / "digisearch/Dockerfile"

#: Canary texts. They travel on the wire, so their absence from the serialised
#: record is a real property and not the trivial one of never having been sent.
CANARY_ALPHA = "ZQX-CANARY-ALPHA-4417-diagnosis"
CANARY_BRAVO = "ZQX-CANARY-BRAVO-9931-genotype"
CANARY_CHARLIE = "ZQX-CANARY-CHARLIE-2718-biometric"

#: Long enough to clear digillm's MIN_DIGEST_KEY_LENGTH floor. A fabricated value:
#: it exists so the test can assert "keyed" rather than "hashed somehow".
PEPPER = "dig-1141-test-pepper-fabricated-value-0001"

#: The shape a sha256 hexdigest takes. Used to prove an ``absent`` record carries no
#: hash at all -- not even one from some other field.
_HEX64 = re.compile(r"[0-9a-f]{64}")

#: Environment that only the remote path has any business reading.
_REMOTE_ENV_VARS = ["OPENAI_API_KEY", "OPENAI_API_BASE", egress.DIGEST_KEY_ENV]


class _EnvReadRecorder(MutableMapping):
    """An ``os.environ`` stand-in that records reads of named keys.

    "The local path read none of the remote variables" is otherwise an assertion
    about code nobody changed. Patching the mapping turns it into a measurement,
    and the test that installs one proves it fires before relying on its silence.
    """

    def __init__(self, real: MutableMapping[str, str], watched: list[str]) -> None:
        self._real = real
        self._watched = set(watched)
        self.reads: list[str] = []

    def __getitem__(self, key: str) -> str:
        if key in self._watched:
            self.reads.append(key)
        return self._real[key]

    def __setitem__(self, key: str, value: str) -> None:
        self._real[key] = value

    def __delitem__(self, key: str) -> None:
        del self._real[key]

    def __iter__(self) -> Iterator[str]:
        return iter(self._real)

    def __len__(self) -> int:
        return len(self._real)


class _FakeEmbeddings:
    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def create(self, *, model: str, input: list[str]) -> Any:
        self.calls.append({"model": model, "input": list(input)})
        return SimpleNamespace(data=[SimpleNamespace(embedding=[0.5, 0.25]) for _ in input])


class _FakeOpenAIClient:
    """Stands in for ``openai.OpenAI``; counts every construction."""

    instances: list[_FakeOpenAIClient] = []

    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs
        self.embeddings = _FakeEmbeddings()
        _FakeOpenAIClient.instances.append(self)


def _install_fake_openai(monkeypatch: pytest.MonkeyPatch) -> type[_FakeOpenAIClient]:
    _FakeOpenAIClient.instances = []
    module = ModuleType("openai")
    module.OpenAI = _FakeOpenAIClient  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "openai", module)
    return _FakeOpenAIClient


def _configure_remote(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fabricated-not-a-real-key")
    monkeypatch.setenv("OPENAI_API_BASE", "https://api.embeddings.example.test/v1")
    monkeypatch.setenv(egress.DIGEST_KEY_ENV, PEPPER)


def _is_requirement(declared: str, package: str) -> bool:
    """True when *declared* names *package*, whatever version specifier follows.

    Comparing the raw string against the bare name reads "digillm>=0.1.0" as an
    absence, which is the failure this whole test exists to catch.
    """
    return declared.split(">")[0].split("=")[0].split("[")[0].strip() == package


@pytest.fixture
def records(monkeypatch: pytest.MonkeyPatch) -> list[egress.EgressRecord]:
    """Capture records in-process, with the JSONL sink pointed away from the repo."""
    captured: list[egress.EgressRecord] = []
    monkeypatch.setenv(egress.EGRESS_LOG_PATH_ENV, "off")
    egress.set_egress_observer(captured.append)
    try:
        yield captured
    finally:
        egress.set_egress_observer(None)


def test_remote_embedding_call_emits_one_record(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    _configure_remote(monkeypatch)
    client_cls = _install_fake_openai(monkeypatch)

    embedder = OpenAIEmbedder()
    vectors = embedder.embed([CANARY_ALPHA, CANARY_BRAVO])

    assert vectors == [[0.5, 0.25], [0.5, 0.25]]
    assert len(client_cls.instances) == 1
    assert len(records) == 1

    record = records[0]
    assert record.destination == "https://api.embeddings.example.test/v1"
    assert record.provider == "openai"
    assert record.model == "text-embedding-3-small"
    assert record.decision is egress.EgressDecision.UNSCREENED
    assert record.category_ids == ()
    assert record.outcome == "succeeded"
    assert record.cache_status == "miss"
    assert record.purpose == CallPurpose.EMBEDDING.value
    assert record.digest_algorithm is egress.DigestAlgorithm.HMAC_SHA256
    assert record.payload_digest is not None
    assert _HEX64.fullmatch(record.payload_digest) is not None
    first_digest = record.payload_digest

    # The same bytes on the wire must produce the same digest, or two records
    # cannot be joined to answer "did we send this twice?".
    records.clear()
    embedder.embed([CANARY_ALPHA, CANARY_BRAVO])
    assert len(records) == 1
    assert records[0].payload_digest == first_digest

    # A different batch must produce a different digest, or the digest carries no
    # information about what was sent.
    records.clear()
    embedder.embed([CANARY_ALPHA, "an entirely unrelated sentence"])
    assert len(records) == 1
    assert records[0].payload_digest != first_digest

    # The client is built once and reused; the repeated calls above are three
    # records over one connection, not three connections.
    assert len(client_cls.instances) == 1


def test_local_embedder_emits_nothing(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    _configure_remote(monkeypatch)
    client_cls = _install_fake_openai(monkeypatch)
    # The remote provider module must not even be *imported* on the local path. The
    # import is what would pull digillm in, so "no record here" would otherwise be a
    # property of the import graph rather than of the local code path.
    monkeypatch.delitem(sys.modules, "digisearch.embedding.providers.openai", raising=False)
    monkeypatch.setattr(
        minilm_module.MiniLMEmbedder,
        "_fn",
        lambda self: lambda texts: [[0.1, 0.2, 0.3] for _ in texts],
    )
    reads = _EnvReadRecorder(os.environ, _REMOTE_ENV_VARS)
    monkeypatch.setattr(os, "environ", reads)

    embedder = minilm_module.get_default_minilm_embedder()
    vectors = embedder.embed([CANARY_ALPHA, CANARY_BRAVO])

    assert vectors == [[0.1, 0.2, 0.3], [0.1, 0.2, 0.3]]
    assert embedder.dimensions == minilm_module.MINILM_DIMENSIONS
    assert records == []
    assert client_cls.instances == []
    assert "digisearch.embedding.providers.openai" not in sys.modules
    assert reads.reads == []

    # Positive control: the recorder above is capable of firing, and fires on the
    # very first remote construction. Without this, `reads.reads == []` would only
    # prove the recorder was watching nothing.
    remote = OpenAIEmbedder()
    assert remote._base_url == "https://api.embeddings.example.test/v1"
    assert set(reads.reads) == {"OPENAI_API_KEY", "OPENAI_API_BASE"}


def test_record_never_carries_the_input_texts(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    _configure_remote(monkeypatch)
    client_cls = _install_fake_openai(monkeypatch)

    embedder = OpenAIEmbedder()
    embedder.embed([CANARY_ALPHA, CANARY_BRAVO, CANARY_CHARLIE])

    # Control: the canaries really did leave. Without it, their absence from the
    # record could mean the batch was empty rather than that the record is clean.
    assert len(client_cls.instances) == 1
    sent = client_cls.instances[0].embeddings.calls
    assert sent == [
        {
            "model": "text-embedding-3-small",
            "input": [CANARY_ALPHA, CANARY_BRAVO, CANARY_CHARLIE],
        }
    ]

    assert len(records) == 1
    serialised = records[0].model_dump_json()
    assert CANARY_ALPHA not in serialised
    assert CANARY_BRAVO not in serialised
    assert CANARY_CHARLIE not in serialised
    # The digest is over that batch, so it is present even though the batch is not.
    assert records[0].payload_digest is not None


@pytest.mark.parametrize(
    "pepper",
    [
        pytest.param(None, id="unset"),
        pytest.param("", id="empty"),
        pytest.param("x" * (egress.MIN_DIGEST_KEY_LENGTH - 1), id="one-char-short"),
        pytest.param(" " * 64, id="whitespace-only"),
    ],
)
def test_absent_pepper_emits_no_digest(
    monkeypatch: pytest.MonkeyPatch,
    records: list[egress.EgressRecord],
    pepper: str | None,
) -> None:
    _configure_remote(monkeypatch)
    if pepper is None:
        monkeypatch.delenv(egress.DIGEST_KEY_ENV, raising=False)
    else:
        monkeypatch.setenv(egress.DIGEST_KEY_ENV, pepper)
    _install_fake_openai(monkeypatch)

    OpenAIEmbedder().embed([CANARY_ALPHA, CANARY_BRAVO])

    # A missing pepper degrades the digest, never the record.
    assert len(records) == 1
    record = records[0]
    assert record.payload_digest is None
    assert record.digest_algorithm is egress.DigestAlgorithm.ABSENT
    line = record.model_dump_json()
    assert _HEX64.search(line) is None


def test_unset_base_url_records_unknown_not_none(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fabricated-not-a-real-key")
    monkeypatch.delenv("OPENAI_API_BASE", raising=False)
    monkeypatch.setenv(egress.DIGEST_KEY_ENV, PEPPER)
    _install_fake_openai(monkeypatch)

    OpenAIEmbedder().embed([CANARY_ALPHA])

    assert len(records) == 1
    # "none" means nothing left the process; this call did. Reporting "none" would
    # delete a real call from the ledger.
    assert records[0].destination == egress.UNKNOWN_DESTINATION
    assert records[0].destination != egress.NO_EGRESS_DESTINATION


@pytest.mark.parametrize(
    ("configured", "expected"),
    [
        (
            "https://user:hunter2@api.example.test/v1",
            "https://api.example.test/v1",
        ),
        (
            "https://api.example.test/v1?api_key=leaked-secret",
            "https://api.example.test/v1",
        ),
        (
            "https://api.example.test:8443/v1#frag",
            "https://api.example.test:8443/v1",
        ),
        ("not-a-url", egress.UNKNOWN_DESTINATION),
    ],
)
def test_destination_strips_credentials(
    monkeypatch: pytest.MonkeyPatch,
    records: list[egress.EgressRecord],
    configured: str,
    expected: str,
) -> None:
    """A record is copied somewhere new; it must not become where secrets go."""
    _configure_remote(monkeypatch)
    monkeypatch.setenv("OPENAI_API_BASE", configured)
    _install_fake_openai(monkeypatch)

    OpenAIEmbedder().embed([CANARY_ALPHA])

    assert len(records) == 1
    assert records[0].destination == expected
    for secret in ("hunter2", "leaked-secret"):
        assert secret not in records[0].model_dump_json()


def test_failed_remote_call_is_recorded_and_reraised(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    _configure_remote(monkeypatch)
    client_cls = _install_fake_openai(monkeypatch)

    def explode(self: object, **_: Any) -> Any:
        raise TimeoutError("simulated provider timeout")

    monkeypatch.setattr(client_cls, "__init__", explode)

    with pytest.raises(TimeoutError):
        OpenAIEmbedder().embed([CANARY_ALPHA])

    # An attempt that failed before the wire is still an attempt. A ledger that
    # omits the calls it cannot prove went is worse than one listing calls it
    # cannot prove did not.
    assert len(records) == 1
    assert records[0].outcome == "failed"
    assert records[0].decision is egress.EgressDecision.UNSCREENED


def test_empty_batch_emits_no_record(
    monkeypatch: pytest.MonkeyPatch, records: list[egress.EgressRecord]
) -> None:
    _configure_remote(monkeypatch)
    client_cls = _install_fake_openai(monkeypatch)

    assert OpenAIEmbedder().embed([]) == []

    # No client was built, so nothing left the process and there is no attempt to
    # describe.
    assert records == []
    assert client_cls.instances == []


def test_digillm_and_openai_are_declared_in_one_extra() -> None:
    """The co-presence the provider's lazy import argument rests on.

    ``openai`` and ``digillm`` must be declared together, because the provider
    imports digillm lazily and only on a path that has already built an openai
    client. Declared apart, that lazy import would be a record that silently stops
    being emitted in exactly the deploys that use it -- which the repository's
    ``pytest.ini`` hides, since it puts ``digillm/src`` on ``pythonpath`` for every
    test regardless of what is installed.
    """
    data = tomllib.loads(_PYPROJECT.read_text(encoding="utf-8"))
    extras: dict[str, list[str]] = data["project"]["optional-dependencies"]
    declared = [req for reqs in extras.values() for req in reqs]
    assert any(_is_requirement(req, "openai") for req in declared), (
        f"openai is not declared in any extra of {_PYPROJECT}"
    )
    assert any(_is_requirement(req, "digillm") for req in declared), (
        f"digillm is not declared in any extra of {_PYPROJECT}"
    )

    with_both = sorted(
        name
        for name, reqs in extras.items()
        if any(_is_requirement(req, "openai") for req in reqs)
        and any(_is_requirement(req, "digillm") for req in reqs)
    )
    assert with_both == ["embedding"], (
        "openai and digillm must be declared in the same extra. Declared apart, the "
        f"provider's lazy digillm import becomes a record that silently stops being "
        f"emitted in exactly the installs that need it; found together in {with_both}"
    )


def test_deployed_image_excludes_the_embedding_extra() -> None:
    """The deployed image is a documented no-op for this path, on purpose.

    ``digisearch/Dockerfile`` installs ``[server,ingestion,azure,chroma,web-search]``.
    The ``embedding`` extra is not among them, so the image has neither ``openai``
    nor ``digillm`` and the remote embedding path cannot run there at all. That is
    the board's decision (DIG-1407): putting digillm in the base dependencies would
    drag ``openai`` in and enable the remote path in the container for the first
    time. If this test ever fails, the image gained the remote embedding path and
    that decision has to be revisited rather than assumed.
    """
    lines = _DOCKERFILE.read_text(encoding="utf-8").splitlines()
    # Only the line that installs digisearch itself carries an extras list; the
    # siblings are bare paths ("-e ./digibase") and would fail to parse as one.
    self_installs = [line for line in lines if re.search(r'-e\s+"\.\[[^"\]]+\]"', line)]
    assert self_installs, f"no extras-bearing editable install found in {_DOCKERFILE}"

    installed: list[str] = []
    for line in self_installs:
        match = re.search(r'"\.\[([^"\]]+)\]"', line)
        assert match is not None, f"could not read the extras out of: {line.strip()}"
        installed.extend(extra.strip() for extra in match.group(1).split(","))
    assert "embedding" not in installed, (
        f"the image now installs [embedding] ({installed}); the remote embedding path "
        "is live in production and this leaf's no-op note is stale"
    )


def test_provider_adds_no_second_digest_implementation() -> None:
    """One record, one digest, one file -- the whole point of reusing digillm."""
    source = _PROVIDER_SOURCE.read_text(encoding="utf-8")
    # Control first: the module really does reuse the shared implementation, so the
    # bans below are not passing because the file records nothing.
    assert "from digillm.egress_record import" in source
    assert "record_egress(" in source

    for banned in ("import hashlib", "import hmac", "compute_payload_digest", "hexdigest"):
        assert banned not in source, (
            f"{banned} in the provider means a second digest implementation, which is "
            "how the two drift and how an unkeyed fallback comes back"
        )
