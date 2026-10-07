"""Pin the security properties of ``scripts/mint_policy_check_token.py`` (DIG-2102).

This is the script that mints the only credential able to read `develop`'s branch
protection, so what is pinned is not its output but its boundaries: the JWT is
RS256 and unpinned-alg-proof, the signature is a real one, the secret never rides
in ``argv``, and the token never reaches stdout. A regression in any of those
would be silent — the guard would keep working against a stale snapshot — so each
is asserted directly rather than inferred from a happy path.
"""

from __future__ import annotations

import base64
import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

pytest.importorskip("cryptography")
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "mint_policy_check_token.py"

pytestmark = pytest.mark.unit

APP_ID = "123456"
INSTALLATION_ID = "654321"
# A distinctive sentinel, deliberately NOT shaped like a real token: a `ghs_`-prefixed
# fixture trips the `github-app-token` gitleaks rule and turns this test file into a
# red gitleaks run. The assertions only need a string that cannot occur by accident.
TOKEN = "SENTINEL-INSTALLATION-TOKEN-VALUE-MUST-NEVER-BE-PRINTED"


def _load() -> ModuleType:
    spec = importlib.util.spec_from_file_location("mint_policy_check_token", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


mint = _load()


@pytest.fixture(scope="module")
def key_pair() -> tuple[rsa.RSAPrivateKey, bytes]:
    """A throwaway RSA key. Generated in-process; never a real credential."""
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    return key, pem


def _segment(jwt: str, index: int) -> dict:
    raw = jwt.split(".")[index]
    padded = raw + "=" * (-len(raw) % 4)
    return json.loads(base64.urlsafe_b64decode(padded))


def test_jwt_is_rs256_and_identifies_the_app(key_pair: tuple) -> None:
    _, pem = key_pair
    jwt = mint.build_jwt(APP_ID, pem, now=1_700_000_000)

    header, claims = _segment(jwt, 0), _segment(jwt, 1)
    assert header == {"alg": "RS256", "typ": "JWT"}
    assert claims["iss"] == APP_ID, "the JWT must identify the App, never a user"
    # The backdated `iat` is deliberate (clock skew), so the span is ttl + skew,
    # and what GitHub's 10-minute cap governs is the distance from *now* to `exp`.
    assert claims["exp"] - claims["iat"] == mint.JWT_TTL_SECONDS + mint.JWT_CLOCK_SKEW_SECONDS
    assert claims["iat"] <= 1_700_000_000, "must be backdated for clock skew"
    assert claims["exp"] - 1_700_000_000 <= 600, "GitHub caps an App JWT at 10 minutes"


def test_jwt_signature_verifies_against_the_public_key(key_pair: tuple) -> None:
    """The signature must be a real RS256 signature, not a well-shaped placeholder."""
    key, pem = key_pair
    jwt = mint.build_jwt(APP_ID, pem, now=1_700_000_000)
    signing_input, signature_b64 = jwt.rsplit(".", 1)

    signature = base64.urlsafe_b64decode(signature_b64 + "=" * (-len(signature_b64) % 4))
    key.public_key().verify(
        signature, signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256()
    )


def test_jwt_alg_is_not_taken_from_caller_input(key_pair: tuple) -> None:
    """`build_jwt` takes no alg parameter, so it cannot be forged into `none`/HS256.

    Pinned structurally: an alg-injection would mean a new keyword argument, and a
    keyword that does not exist is a TypeError rather than a silent downgrade.
    """
    _, pem = key_pair
    with pytest.raises(TypeError):
        mint.build_jwt(APP_ID, pem, algorithm="none")  # type: ignore[call-arg]


def test_non_rsa_private_key_is_refused() -> None:
    from cryptography.hazmat.primitives.asymmetric import ed25519

    ed = ed25519.Ed25519PrivateKey.generate()
    pem = ed.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption(),
    )
    with pytest.raises(mint.MintError, match="not an RSA key"):
        mint.build_jwt(APP_ID, pem)


def test_secret_is_not_accepted_as_an_argv_value() -> None:
    """`--private-key` must not exist: argv is readable by any process in `ps`."""
    parsed = mint._parser().parse_args([])
    assert not hasattr(parsed, "private_key")
    with pytest.raises(SystemExit):
        mint._parser().parse_args(["--private-key", "-----BEGIN RSA PRIVATE KEY-----"])


def test_verify_prints_the_contexts_but_never_the_token(
    key_pair: tuple, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """The one read the guard needs must succeed loudly, and the token must not leak."""
    _, pem = key_pair
    contexts = ["Required checks passed", "doc-links + agents-init", "mypy — digibase + digikey"]

    monkeypatch.setattr(mint, "mint_token", lambda *a, **k: (TOKEN, "2026-10-07T21:00:00Z"))
    monkeypatch.setattr(mint, "read_required_contexts", lambda *a, **k: list(contexts))
    monkeypatch.setenv(mint.PRIVATE_KEY_ENV, pem.decode("utf-8"))

    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])
    out = capsys.readouterr().out

    assert exit_code == mint.OK
    assert TOKEN not in out, "the installation token must never reach stdout"
    assert TOKEN not in out.replace("\n", ""), "nor via line-wrapping tricks"
    for context in contexts:
        assert context in out


def test_missing_grant_fails_loudly_rather_than_reporting_success(
    key_pair: tuple, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A token that mints but cannot read branch protection is a FAILED credential.

    This is the case the whole credential exists to detect: a stale snapshot is
    otherwise indistinguishable from a correct one, so the probe must not pass.
    """
    _, pem = key_pair
    monkeypatch.setattr(mint, "mint_token", lambda *a, **k: (TOKEN, "2026-10-07T21:00:00Z"))

    def _refused(*_a: object, **_k: object) -> list[str]:
        raise mint.MintError("GET /repos/.../protection -> HTTP 403 Forbidden")

    monkeypatch.setattr(mint, "read_required_contexts", _refused)
    monkeypatch.setenv(mint.PRIVATE_KEY_ENV, pem.decode("utf-8"))

    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])
    captured = capsys.readouterr()

    assert exit_code == mint.FAILED
    assert TOKEN not in captured.out
    assert TOKEN not in captured.err
    assert "Administration: read" in captured.err


def test_missing_key_is_a_setup_error_not_a_credential_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """Absent secret -> SETUP_ERROR. Exit 1 is reserved for a credential proven wrong."""
    monkeypatch.delenv(mint.PRIVATE_KEY_ENV, raising=False)
    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])
    captured = capsys.readouterr()

    assert exit_code == mint.SETUP_ERROR
    assert mint.SETUP_ERROR != mint.FAILED
    assert mint.PRIVATE_KEY_ENV in captured.err
