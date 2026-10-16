"""Contract tests for the K3 AES-256-GCM credential envelope.

Four things are pinned here, in rough order of how much a human reviewer should care:

1. **Fail closed.** A wrong master key, a wrong AAD component, a truncated ciphertext, a
   flipped bit in either the body or the tag, and a mismatched ``key_id`` all raise —
   nothing returns partial or attacker-chosen plaintext.
2. **Plaintext never escapes.** ``test_plaintext_never_appears_in_any_observable_surface``
   captures logging around a full seal/open cycle including every failure path, then
   asserts the secret is absent from every log record, ``repr``, ``str``, and formatted
   traceback the module can produce.
3. **The committed vectors are exact.** Sealing each vector's plaintext under its key,
   nonce and AAD reproduces the committed ciphertext byte-for-byte, and opening the
   committed ciphertext reproduces the plaintext. This is the suite the future TypeScript
   Edge Function implementation must also pass (see ``vectors.json``'s ``_readme``).
4. **The master key is mandatory and well-formed.** Missing, non-base64, and wrong-length
   values each raise a configuration error that does not echo the value.
"""

# score:allow untyped any
# `Any` below annotates the deserialized `vectors.json` mapping only. Narrowing it to
# `object` would put a cast in front of every vector lookup without making the assertions
# any stronger; the production vault carries no `Any` at all.

from __future__ import annotations

import json
import logging
import traceback
from pathlib import Path
from typing import Any, Literal

import pytest
from digiquant.vault import (
    MASTER_KEY_BYTES,
    MASTER_KEY_ENV,
    NONCE_BYTES,
    ApiKeyCredential,
    CredentialLeaseExpiredError,
    EnvelopeAuthenticationError,
    MasterKey,
    OAuthCredential,
    SealedEnvelope,
    VaultConfigurationError,
    VaultKeyMismatchError,
    VaultPayloadError,
    build_aad,
    canonical_json,
    fingerprint,
    load_master_key,
    open_bytes,
    parse_credential,
    seal_bytes,
    seal_credential,
    unseal_credential,
)
from digiquant.vault.envelope import (
    _CREDENTIAL_ADAPTER,
    KEY_ID_ENV,
    _CredentialPayload,
    _seal_bytes_with_nonce,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

VECTORS_PATH = Path(__file__).with_name("vectors.json")

WORKSPACE_A = "11111111-1111-4111-8111-111111111111"
WORKSPACE_B = "22222222-2222-4222-8222-222222222222"

# Distinct, obviously-synthetic keys. Never the ones in vectors.json, so a test that
# accidentally depended on vector key material would fail rather than silently pass.
KEY_ONE = MasterKey(key_id="v1", material=bytes([0x11]) * MASTER_KEY_BYTES)
KEY_TWO = MasterKey(key_id="v2", material=bytes([0x22]) * MASTER_KEY_BYTES)


@pytest.fixture
def credential() -> ApiKeyCredential:
    return ApiKeyCredential(key_id="unit-key-id", secret="unit-test-plaintext-secret")


@pytest.fixture
def aad() -> bytes:
    return build_aad(WORKSPACE_A, "alpaca", "paper")


@pytest.fixture(scope="module")
def vectors() -> dict[str, Any]:
    return json.loads(VECTORS_PATH.read_text(encoding="utf-8"))


# --- master key -------------------------------------------------------------------


def test_missing_master_key_fails_closed() -> None:
    with pytest.raises(VaultConfigurationError) as excinfo:
        load_master_key({})
    assert MASTER_KEY_ENV in str(excinfo.value)


@pytest.mark.parametrize("blank", ["", "   "])
def test_blank_master_key_fails_closed(blank: str) -> None:
    with pytest.raises(VaultConfigurationError):
        load_master_key({MASTER_KEY_ENV: blank})


def test_non_base64_master_key_fails_closed_without_echoing_the_value() -> None:
    bogus = "not-base64-!!!"
    with pytest.raises(VaultConfigurationError) as excinfo:
        load_master_key({MASTER_KEY_ENV: bogus})
    assert bogus not in str(excinfo.value)
    # Also assert the traceback: the implementation raises `from None` here so no library
    # message can contribute text, and this pins that the whole rendered failure is clean
    # even if binascii's wording changes.
    assert bogus not in "".join(traceback.format_exception(excinfo.value))


@pytest.mark.parametrize("byte_length", [16, 24, 31, 33, 64])
def test_wrong_length_master_key_fails_closed(byte_length: int) -> None:
    import base64

    encoded = base64.b64encode(bytes(byte_length)).decode()
    with pytest.raises(VaultConfigurationError) as excinfo:
        load_master_key({MASTER_KEY_ENV: encoded})
    assert str(byte_length) in str(excinfo.value)


def test_exactly_32_bytes_loads_with_the_declared_key_id() -> None:
    import base64

    encoded = base64.b64encode(bytes(range(MASTER_KEY_BYTES))).decode()
    key = load_master_key({MASTER_KEY_ENV: encoded, KEY_ID_ENV: "v7"})
    assert key.key_id == "v7"
    assert len(key.material) == MASTER_KEY_BYTES


def test_key_id_defaults_to_v1() -> None:
    import base64

    encoded = base64.b64encode(bytes(range(MASTER_KEY_BYTES))).decode()
    assert load_master_key({MASTER_KEY_ENV: encoded}).key_id == "v1"


@pytest.mark.parametrize("bad_key_id", ["V1", "-v1", "v1 2", "a" * 33, "v/1"])
def test_malformed_key_id_fails_closed(bad_key_id: str) -> None:
    import base64

    encoded = base64.b64encode(bytes(range(MASTER_KEY_BYTES))).decode()
    with pytest.raises(VaultConfigurationError):
        load_master_key({MASTER_KEY_ENV: encoded, KEY_ID_ENV: bad_key_id})


def test_master_key_repr_never_shows_material() -> None:
    assert repr(KEY_ONE) == "MasterKey(key_id='v1')"
    assert KEY_ONE.material.hex() not in repr(KEY_ONE)


# --- AAD --------------------------------------------------------------------------


def test_aad_is_the_documented_concatenation() -> None:
    assert build_aad(WORKSPACE_A, "alpaca", "paper") == f"{WORKSPACE_A}:alpaca:paper".encode()


@pytest.mark.parametrize(
    ("workspace_id", "broker", "env"),
    [
        ("", "alpaca", "paper"),
        ("   ", "alpaca", "paper"),
        (WORKSPACE_A, "", "paper"),
        (WORKSPACE_A, "alpaca", ""),
    ],
)
def test_aad_rejects_empty_components(workspace_id: str, broker: str, env: str) -> None:
    with pytest.raises(ValueError):
        build_aad(workspace_id, broker, env)


@pytest.mark.parametrize(
    ("workspace_id", "broker", "env"),
    [
        ("ws:1", "alpaca", "paper"),
        (WORKSPACE_A, "al:paca", "paper"),
        (WORKSPACE_A, "alpaca", "pa:per"),
    ],
)
def test_aad_rejects_colons_so_the_binding_stays_unambiguous(
    workspace_id: str, broker: str, env: str
) -> None:
    """Without this rule ``("a:b", "c", …)`` and ``("a", "b:c", …)`` share an AAD, and a
    ciphertext could be replayed between those two row identities."""
    with pytest.raises(ValueError, match="':'"):
        build_aad(workspace_id, broker, env)


# --- round trip -------------------------------------------------------------------


def test_round_trip_returns_the_same_credential(credential: ApiKeyCredential, aad: bytes) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    with unseal_credential(envelope, aad=aad, key=KEY_ONE) as lease:
        assert lease.credential == credential
        assert lease.fingerprint == fingerprint(credential)


def test_oauth_round_trip_preserves_optional_refresh_token(aad: bytes) -> None:
    credential = OAuthCredential(access_token="access-abc", refresh_token="refresh-def")
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    with unseal_credential(envelope, aad=aad, key=KEY_ONE) as lease:
        opened = lease.credential
    assert isinstance(opened, OAuthCredential)
    assert opened.refresh_token == "refresh-def"


def test_absent_refresh_token_is_omitted_not_nulled() -> None:
    """The canonical plaintext has no ``"refresh_token":null`` — that is the byte-level
    contract the TypeScript implementation has to match."""
    assert (
        canonical_json(OAuthCredential(access_token="a")) == b'{"access_token":"a","kind":"oauth"}'
    )


def test_canonical_json_sorts_keys_and_omits_whitespace(credential: ApiKeyCredential) -> None:
    raw = canonical_json(credential).decode()
    assert raw.startswith('{"key_id":')
    assert " " not in raw
    assert list(json.loads(raw)) == sorted(json.loads(raw))


def test_every_seal_uses_a_fresh_nonce(credential: ApiKeyCredential, aad: bytes) -> None:
    """Nonce reuse under one key breaks GCM, so this is a security property, not style."""
    nonces = {seal_credential(credential, aad=aad, key=KEY_ONE).nonce for _ in range(32)}
    assert len(nonces) == 32


def test_nonce_is_96_bit(credential: ApiKeyCredential, aad: bytes) -> None:
    assert len(seal_credential(credential, aad=aad, key=KEY_ONE).nonce) == NONCE_BYTES


def test_seal_rejects_an_unvalidated_mapping(aad: bytes) -> None:
    """The seal path takes model instances only, so no ``ValidationError`` (whose message
    echoes its input) is ever raised over plaintext here."""
    with pytest.raises(TypeError):
        seal_credential({"kind": "api_key", "key_id": "k", "secret": "s"}, aad=aad, key=KEY_ONE)  # type: ignore[arg-type]


def test_envelope_layer_is_credential_agnostic(aad: bytes) -> None:
    """T2/T4 will seal their own payload shapes through ``seal_bytes``."""
    payload = b'{"provider":"groq","api_key":"byok-placeholder"}'
    envelope = seal_bytes(payload, aad=aad, key=KEY_ONE)
    assert open_bytes(envelope, aad=aad, key=KEY_ONE) == payload


@pytest.mark.parametrize("plaintext", [b"", "not bytes"])
def test_seal_rejects_empty_or_non_bytes_plaintext(plaintext: object, aad: bytes) -> None:
    with pytest.raises(ValueError):
        seal_bytes(plaintext, aad=aad, key=KEY_ONE)  # type: ignore[arg-type]


def test_seal_rejects_oversized_plaintext(aad: bytes) -> None:
    with pytest.raises(ValueError, match="exceeds"):
        seal_bytes(b"x" * 8193, aad=aad, key=KEY_ONE)


# --- fail closed ------------------------------------------------------------------


def test_wrong_master_key_fails_closed(credential: ApiKeyCredential, aad: bytes) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    # Same key_id, different material: isolates the tag check from the key_id guard.
    impostor = MasterKey(key_id=KEY_ONE.key_id, material=bytes([0x33]) * MASTER_KEY_BYTES)
    with pytest.raises(EnvelopeAuthenticationError):
        open_bytes(envelope, aad=aad, key=impostor)


def test_mismatched_key_id_fails_closed_before_decrypting(
    credential: ApiKeyCredential, aad: bytes
) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    with pytest.raises(VaultKeyMismatchError) as excinfo:
        open_bytes(envelope, aad=aad, key=KEY_TWO)
    assert "v1" in str(excinfo.value) and "v2" in str(excinfo.value)


@pytest.mark.parametrize(
    "wrong_aad_parts",
    [
        (WORKSPACE_B, "alpaca", "paper"),
        (WORKSPACE_A, "ibkr", "paper"),
        (WORKSPACE_A, "alpaca", "live"),
    ],
    ids=["other_workspace", "other_broker", "other_env"],
)
def test_wrong_aad_fails_closed(
    credential: ApiKeyCredential, aad: bytes, wrong_aad_parts: tuple[str, str, str]
) -> None:
    """This is the replay protection: a row's ciphertext is not openable under another
    row's (workspace_id, broker, env) identity."""
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    with pytest.raises(EnvelopeAuthenticationError):
        open_bytes(envelope, aad=build_aad(*wrong_aad_parts), key=KEY_ONE)


def test_truncated_ciphertext_fails_closed(credential: ApiKeyCredential, aad: bytes) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    truncated = SealedEnvelope(
        ciphertext=envelope.ciphertext[:-1],
        nonce=envelope.nonce,
        key_id=envelope.key_id,
    )
    with pytest.raises(EnvelopeAuthenticationError):
        open_bytes(truncated, aad=aad, key=KEY_ONE)


def test_ciphertext_shorter_than_the_tag_is_rejected_at_the_model_boundary() -> None:
    """16 bytes or fewer cannot hold a payload at all — reject before reaching AES."""
    with pytest.raises(ValidationError):
        SealedEnvelope(ciphertext=bytes(16), nonce=bytes(NONCE_BYTES), key_id="v1")


@pytest.mark.parametrize("index", [0, -1], ids=["body_bit", "tag_bit"])
def test_flipped_bit_fails_closed(credential: ApiKeyCredential, aad: bytes, index: int) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    mutated = bytearray(envelope.ciphertext)
    mutated[index] ^= 0x01
    tampered = SealedEnvelope(
        ciphertext=bytes(mutated),
        nonce=envelope.nonce,
        key_id=envelope.key_id,
    )
    with pytest.raises(EnvelopeAuthenticationError):
        open_bytes(tampered, aad=aad, key=KEY_ONE)


def test_wrong_nonce_fails_closed(credential: ApiKeyCredential, aad: bytes) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    swapped = SealedEnvelope(
        ciphertext=envelope.ciphertext,
        nonce=bytes(NONCE_BYTES),
        key_id=envelope.key_id,
    )
    with pytest.raises(EnvelopeAuthenticationError):
        open_bytes(swapped, aad=aad, key=KEY_ONE)


@pytest.mark.parametrize("bad_nonce_length", [0, 11, 13, 16])
def test_wrong_nonce_length_is_rejected_at_the_model_boundary(bad_nonce_length: int) -> None:
    with pytest.raises(ValidationError):
        SealedEnvelope(ciphertext=bytes(32), nonce=bytes(bad_nonce_length), key_id="v1")


def test_authentic_bytes_that_are_not_a_credential_fail_closed(aad: bytes) -> None:
    """Authenticity is not validity: a legitimately sealed non-credential payload is
    rejected as a payload error, and the rejected content is not echoed."""
    envelope = seal_bytes(
        b'{"kind":"totally_unknown","secret":"leak-me-if-you-can"}', aad=aad, key=KEY_ONE
    )
    with pytest.raises(VaultPayloadError) as excinfo:
        with unseal_credential(envelope, aad=aad, key=KEY_ONE):
            pass
    rendered = str(excinfo.value) + "".join(traceback.format_exception(excinfo.value))
    assert "leak-me-if-you-can" not in rendered


def test_payload_error_has_no_validation_context_carrying_secrets(aad: bytes) -> None:
    """``raise … from None`` only suppresses display; ``__context__`` must also be cleared.

    Pydantic's ``ValidationError.errors()`` embeds the rejected input (the decrypted JSON),
    so leaving that error on ``__context__`` would keep the secret reachable on the
    authentic-but-wrong-shape path even when the traceback looks clean.
    """
    secret = "leak-me-via-context-chain"
    # Missing ``key_id``: ValidationError.errors() includes the whole input dict (secret).
    envelope = seal_bytes(
        f'{{"kind":"api_key","secret":"{secret}"}}'.encode(),
        aad=aad,
        key=KEY_ONE,
    )
    with pytest.raises(VaultPayloadError) as excinfo:
        with unseal_credential(envelope, aad=aad, key=KEY_ONE):
            pass
    exc = excinfo.value
    assert exc.__context__ is None
    assert exc.__cause__ is None
    chain = "".join(traceback.format_exception(exc))
    assert secret not in chain
    assert secret not in repr(exc.__context__)


def test_parse_credential_accepts_valid_mappings() -> None:
    oauth = parse_credential({"kind": "oauth", "access_token": "tok"})
    assert isinstance(oauth, OAuthCredential)
    assert oauth.access_token == "tok"
    api = parse_credential({"kind": "api_key", "key_id": "k", "secret": "s"})
    assert isinstance(api, ApiKeyCredential)
    assert api.secret == "s"


def test_parse_credential_raises_context_free_vault_payload_error() -> None:
    """Ingest (T3) must use parse_credential so ValidationError never escapes with secrets."""
    secret = "ingest-surface-must-not-echo-me"
    with pytest.raises(VaultPayloadError) as excinfo:
        parse_credential({"kind": "api_key", "secret": secret})
    exc = excinfo.value
    assert exc.__context__ is None
    assert exc.__cause__ is None
    assert secret not in str(exc)
    assert secret not in "".join(traceback.format_exception(exc))
    assert secret not in repr(exc.__context__)


# --- lease lifetime ---------------------------------------------------------------


def test_lease_is_dead_after_the_with_block(credential: ApiKeyCredential, aad: bytes) -> None:
    """The rule "callers must not persist plaintext" is enforced, not just documented."""
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    with unseal_credential(envelope, aad=aad, key=KEY_ONE) as lease:
        assert lease.credential.secret == credential.secret
    with pytest.raises(CredentialLeaseExpiredError):
        _ = lease.credential
    # The display-safe label survives — it is what a caller is meant to keep.
    assert lease.fingerprint == fingerprint(credential)


def test_lease_is_closed_even_when_the_body_raises(
    credential: ApiKeyCredential, aad: bytes
) -> None:
    envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
    escaped = None
    with pytest.raises(RuntimeError):
        with unseal_credential(envelope, aad=aad, key=KEY_ONE) as lease:
            escaped = lease
            raise RuntimeError("boom")
    assert escaped is not None
    with pytest.raises(CredentialLeaseExpiredError):
        _ = escaped.credential


# --- fingerprint ------------------------------------------------------------------


def test_fingerprint_is_eight_lowercase_hex_of_the_secret_material() -> None:
    import hashlib

    credential = ApiKeyCredential(key_id="k", secret="s3cret")
    expected = hashlib.sha256(b"s3cret").hexdigest()[:8]
    assert fingerprint(credential) == expected
    assert len(expected) == 8


def test_oauth_fingerprint_digests_the_access_token() -> None:
    import hashlib

    credential = OAuthCredential(access_token="access-abc", refresh_token="refresh-def")
    assert fingerprint(credential) == hashlib.sha256(b"access-abc").hexdigest()[:8]


def test_fingerprint_is_stable_and_distinguishes_different_secrets() -> None:
    one = ApiKeyCredential(key_id="k", secret="alpha")
    two = ApiKeyCredential(key_id="k", secret="beta")
    assert fingerprint(one) == fingerprint(one)
    assert fingerprint(one) != fingerprint(two)


# --- payload schema ---------------------------------------------------------------


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "api_key", "key_id": "k", "secret": "s", "extra": "nope"},
        {"kind": "oauth", "access_token": "a", "scope": "trading"},
    ],
)
def test_payload_models_forbid_unknown_fields(payload: dict[str, str]) -> None:
    from digiquant.vault.envelope import _CREDENTIAL_ADAPTER

    with pytest.raises(ValidationError):
        _CREDENTIAL_ADAPTER.validate_python(payload)


@pytest.mark.parametrize(
    "payload",
    [
        {"kind": "api_key", "key_id": "", "secret": "s"},
        {"kind": "api_key", "key_id": "k", "secret": ""},
        {"kind": "oauth", "access_token": ""},
        {"kind": "oauth"},
        {"kind": "api_key", "secret": "s"},
        {"kind": "unknown", "secret": "s"},
    ],
)
def test_payload_models_reject_incomplete_credentials(payload: dict[str, str]) -> None:
    with pytest.raises(ValidationError):
        _CREDENTIAL_ADAPTER.validate_python(payload)


def test_payloads_are_frozen(credential: ApiKeyCredential) -> None:
    with pytest.raises(ValidationError):
        credential.secret = "rewritten"  # type: ignore[misc]


def test_payload_without_secret_material_cannot_be_instantiated() -> None:
    """A new credential kind must say what its secret is before it can exist.

    Otherwise the gap surfaces as a wrong fingerprint (or a leak through an inherited
    ``repr``) at the first real credential, rather than at the class definition.
    """

    class NoSecretMaterial(_CredentialPayload):
        kind: Literal["no_secret_material"] = "no_secret_material"

    with pytest.raises(TypeError, match="secret_material"):
        NoSecretMaterial()


# --- committed test vectors -------------------------------------------------------


def test_vectors_file_states_the_cross_implementation_contract(vectors: dict[str, Any]) -> None:
    """The header is load-bearing: it is what tells a TS implementer this suite is
    mandatory, so a silent rewrite that drops it should fail here."""
    readme = " ".join(vectors["_readme"])
    assert "implementation of record" in readme
    assert "Edge Function" in readme
    assert "MUST pass this" in readme
    assert vectors["algorithm"]["name"] == "AES-256-GCM"
    assert vectors["algorithm"]["nonce_bytes"] == NONCE_BYTES
    assert vectors["algorithm"]["tag_bytes"] == 16


def _vector_key(vectors: dict[str, Any], key_id: str) -> MasterKey:
    material = bytes.fromhex(vectors["keys"][key_id]["hex"])
    assert len(material) == MASTER_KEY_BYTES
    return MasterKey(key_id=key_id, material=material)


def _vector_ids(vectors: dict[str, Any]) -> list[str]:
    return [vector["name"] for vector in vectors["vectors"]]


def test_vectors_cover_both_payload_kinds_and_both_keys(vectors: dict[str, Any]) -> None:
    names = _vector_ids(vectors)
    assert len(names) == len(set(names)) >= 6
    kinds = {
        json.loads(v["plaintext_utf8"]).get("kind")
        for v in vectors["vectors"]
        if v["plaintext_utf8"].startswith("{")
    }
    assert {"oauth", "api_key"} <= kinds
    assert {v["key_id"] for v in vectors["vectors"]} == {"v1", "v2"}


def test_committed_vectors_seal_to_the_committed_ciphertext(vectors: dict[str, Any]) -> None:
    """Deterministic re-seal under each vector's own nonce must be byte-identical. This is
    the assertion the TypeScript implementation has to reproduce."""
    for vector in vectors["vectors"]:
        key = _vector_key(vectors, vector["key_id"])
        parts = vector["aad_parts"]
        aad = build_aad(parts["workspace_id"], parts["broker"], parts["env"])
        assert aad == vector["aad"].encode(), vector["name"]
        sealed = _seal_bytes_with_nonce(
            vector["plaintext_utf8"].encode(),
            nonce=bytes.fromhex(vector["nonce_hex"]),
            aad=aad,
            key=key,
        )
        assert sealed.ciphertext.hex() == vector["ciphertext_hex"], vector["name"]


def test_committed_vectors_open_to_the_committed_plaintext(vectors: dict[str, Any]) -> None:
    for vector in vectors["vectors"]:
        key = _vector_key(vectors, vector["key_id"])
        parts = vector["aad_parts"]
        envelope = SealedEnvelope(
            ciphertext=bytes.fromhex(vector["ciphertext_hex"]),
            nonce=bytes.fromhex(vector["nonce_hex"]),
            key_id=vector["key_id"],
        )
        opened = open_bytes(
            envelope,
            aad=build_aad(parts["workspace_id"], parts["broker"], parts["env"]),
            key=key,
        )
        assert opened.decode() == vector["plaintext_utf8"], vector["name"]


def test_credential_vectors_round_trip_through_the_typed_layer(vectors: dict[str, Any]) -> None:
    for vector in vectors["vectors"]:
        if vector["fingerprint"] is None:
            continue
        key = _vector_key(vectors, vector["key_id"])
        parts = vector["aad_parts"]
        aad = build_aad(parts["workspace_id"], parts["broker"], parts["env"])
        envelope = SealedEnvelope(
            ciphertext=bytes.fromhex(vector["ciphertext_hex"]),
            nonce=bytes.fromhex(vector["nonce_hex"]),
            key_id=vector["key_id"],
        )
        with unseal_credential(envelope, aad=aad, key=key) as lease:
            assert lease.fingerprint == vector["fingerprint"], vector["name"]
            assert canonical_json(lease.credential).decode() == vector["plaintext_utf8"]


def test_every_declared_negative_case_actually_fails_closed(vectors: dict[str, Any]) -> None:
    """The negative cases are part of the cross-implementation contract, so each declared
    mutation is executed here rather than trusted as documentation."""
    by_name = {vector["name"]: vector for vector in vectors["vectors"]}
    assert vectors["negative_cases"]

    for case in vectors["negative_cases"]:
        vector = by_name[case["vector"]]
        parts = dict(vector["aad_parts"])
        key = _vector_key(vectors, vector["key_id"])
        ciphertext = bytearray.fromhex(vector["ciphertext_hex"])

        if case["mutation"] == "wrong_key":
            key = _vector_key(vectors, "v2" if vector["key_id"] == "v1" else "v1")
            key = MasterKey(key_id=vector["key_id"], material=key.material)
        elif case["mutation"] == "wrong_aad_workspace":
            parts["workspace_id"] = WORKSPACE_B
        elif case["mutation"] == "wrong_aad_env":
            parts["env"] = "live"
        elif case["mutation"] == "truncated_ciphertext":
            ciphertext = ciphertext[:-1]
        elif case["mutation"] == "flipped_tag_bit":
            ciphertext[-1] ^= 0x01
        elif case["mutation"] == "flipped_body_bit":
            ciphertext[0] ^= 0x01
        else:  # pragma: no cover - a new mutation must be implemented, not skipped
            raise AssertionError(f"unhandled negative mutation {case['mutation']!r}")

        envelope = SealedEnvelope(
            ciphertext=bytes(ciphertext),
            nonce=bytes.fromhex(vector["nonce_hex"]),
            key_id=vector["key_id"],
        )
        with pytest.raises(EnvelopeAuthenticationError):
            open_bytes(
                envelope,
                aad=build_aad(parts["workspace_id"], parts["broker"], parts["env"]),
                key=key,
            )


# --- plaintext absence ------------------------------------------------------------


def test_plaintext_never_appears_in_any_observable_surface(
    caplog: pytest.LogCaptureFixture, aad: bytes
) -> None:
    """Exercise every path the module has — happy and failing — then assert the secret is
    absent from every log record, ``repr``, ``str``, and formatted traceback produced.

    Log capture is at DEBUG on the root logger, so a stray ``logger.debug`` added to the
    envelope later is caught by this test rather than shipping quietly.
    """
    secret = "PLAINTEXT-a1b2c3-must-never-be-observable"
    broker_key_id = "PLAINTEXT-broker-key-id-d4e5f6"
    credential = ApiKeyCredential(key_id=broker_key_id, secret=secret)
    forbidden = (secret, broker_key_id)
    observed: list[str] = []

    with caplog.at_level(logging.DEBUG):
        envelope = seal_credential(credential, aad=aad, key=KEY_ONE)
        observed += [repr(credential), str(credential), repr(envelope), str(envelope)]
        observed.append(repr(KEY_ONE))

        with unseal_credential(envelope, aad=aad, key=KEY_ONE) as lease:
            observed += [repr(lease), str(lease), lease.fingerprint]
            # Sanity: the secret really is reachable inside the lease, so the assertions
            # below are about surfaces, not about a test that sealed the wrong thing.
            assert lease.credential.secret == secret
        observed += [repr(lease), str(lease)]

        wrong_shape = seal_bytes(
            f'{{"kind":"api_key","secret":"{secret}"}}'.encode(),
            aad=aad,
            key=KEY_ONE,
        )
        for failure in (
            lambda: open_bytes(
                envelope, aad=build_aad(WORKSPACE_B, "alpaca", "paper"), key=KEY_ONE
            ),
            lambda: open_bytes(envelope, aad=aad, key=KEY_TWO),
            lambda: open_bytes(
                SealedEnvelope(
                    ciphertext=envelope.ciphertext[:-1],
                    nonce=envelope.nonce,
                    key_id=envelope.key_id,
                ),
                aad=aad,
                key=KEY_ONE,
            ),
            lambda: lease.credential,
            lambda: load_master_key({MASTER_KEY_ENV: secret}),
            lambda: unseal_credential(wrong_shape, aad=aad, key=KEY_ONE).__enter__(),
            lambda: parse_credential({"kind": "api_key", "secret": secret}),
        ):
            # Intentionally broad: the probe is "whatever this raises must not leak",
            # so pinning the type per lambda would narrow what the test is asserting.
            with pytest.raises(Exception) as excinfo:
                failure()
            observed.append(str(excinfo.value))
            observed.append(repr(excinfo.value))
            observed.append("".join(traceback.format_exception(excinfo.value)))
            # ``raise … from None`` still leaves ``__context__``; assert secrets are not
            # reachable there either (VaultPayloadError must clear it entirely).
            observed.append(repr(excinfo.value.__context__))
            observed.append(repr(excinfo.value.__cause__))

    for record in caplog.records:
        observed += [record.getMessage(), str(record.args), record.name]

    haystack = "\n".join(observed)
    for leak in forbidden:
        assert leak not in haystack, f"{leak!r} escaped into an observable surface"
    # The ciphertext is not plaintext, but assert the sealed bytes did not leak either.
    assert envelope.ciphertext.hex() not in haystack
    assert KEY_ONE.material.hex() not in haystack
