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
from urllib.error import URLError

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
        raise mint.ApiError("GET /repos/.../protection -> HTTP 403 Forbidden")

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


# --------------------------------------------------------------------------
# "I could not tell" must never be reported as "the credential is bad".
#
# Rotation deletes the previous key only once the new one is proven, so an
# outcome that proves nothing must not exit on the code that means "proven
# wrong". Each test below drives one way the read can fail to *prove*, and
# asserts the exit code that keeps an operator from destroying a working key.
# --------------------------------------------------------------------------


def _install_key(monkeypatch: pytest.MonkeyPatch, pem: bytes, *, mint_ok: bool = True) -> None:
    monkeypatch.setenv(mint.PRIVATE_KEY_ENV, pem.decode("utf-8"))
    if mint_ok:
        monkeypatch.setattr(mint, "mint_token", lambda *a, **k: (TOKEN, "2026-10-07T21:00:00Z"))


def test_encrypted_private_key_is_a_setup_error_not_a_credential_failure(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A passphrase-protected key raises ValueError. That is a setup problem.

    Nothing about the key's authorisation was proven wrong, so exit 1 — the code
    that says "this credential is bad, rotate it" — would be a lie.
    """
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pem = key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.BestAvailableEncryption(b"not-the-passphrase"),
    )
    monkeypatch.setenv(mint.PRIVATE_KEY_ENV, pem.decode("utf-8"))

    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])

    assert exit_code == mint.SETUP_ERROR, "an encrypted key is unreadable, not revoked"
    assert exit_code != mint.FAILED
    assert capsys.readouterr().err


def test_a_non_json_response_body_is_a_setup_error(
    key_pair: tuple, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """HTTP 200 with a body that is not the protection JSON proves nothing.

    A captive portal, a proxy, or a future API change would all land here, and
    all three are "the answer is unknown" rather than "the key was rejected".
    """
    _, pem = key_pair
    _install_key(monkeypatch, pem)

    def _garbage(*_a: object, **_k: object) -> list[str]:
        # Exactly what `json.loads` raises inside `_api` for a body that is not JSON.
        raise json.JSONDecodeError("Expecting value", "<html>not json</html>", 0)

    monkeypatch.setattr(mint, "read_required_contexts", _garbage)
    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])

    assert exit_code == mint.SETUP_ERROR
    assert capsys.readouterr().err


def test_a_transport_failure_is_a_setup_error(
    key_pair: tuple, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """A DNS or TCP failure never reached GitHub, so it says nothing about the grant."""
    _, pem = key_pair
    _install_key(monkeypatch, pem)

    def _unreachable(*_a: object, **_k: object) -> list[str]:
        raise URLError("[Errno 8] nodename nor servname provided")

    monkeypatch.setattr(mint, "read_required_contexts", _unreachable)
    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])

    assert exit_code == mint.SETUP_ERROR
    assert exit_code != mint.FAILED
    assert "not evidence that the snapshot is stale" in capsys.readouterr().err


def test_a_mint_failure_is_not_reported_as_a_missing_grant(
    key_pair: tuple, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture
) -> None:
    """An unauthenticated mint is a broken key, and it must say so plainly."""
    _, pem = key_pair
    monkeypatch.setenv(mint.PRIVATE_KEY_ENV, pem.decode("utf-8"))

    def _rejected(*_a: object, **_k: object) -> tuple[str, str]:
        raise mint.ApiError("POST /app/installations/…/access_tokens -> HTTP 401 Unauthorized")

    monkeypatch.setattr(mint, "mint_token", _rejected)
    exit_code = mint.main(["--app-id", APP_ID, "--installation-id", INSTALLATION_ID, "--verify"])

    assert exit_code == mint.FAILED
    err = capsys.readouterr().err
    assert TOKEN not in err
    assert "did not authenticate" in err


def test_a_caller_cannot_widen_the_token_lifetime(key_pair: tuple) -> None:
    """`ttl` is capped at the constant, so no caller can ask for a long-lived JWT.

    GitHub rejects an App JWT more than 10 minutes old; a JWT that overshoots gets
    a 401 that reads exactly like a revoked key, which is the worst possible
    failure mode for a credential whose rotation path is "delete the old key last".
    """
    _, pem = key_pair
    jwt = mint.build_jwt(APP_ID, pem, now=1_700_000_000, ttl=86_400)
    claims = _segment(jwt, 1)

    assert claims["exp"] - 1_700_000_000 <= 600, "an App JWT may not live past 10 minutes"


def test_a_redirect_off_github_is_refused(monkeypatch: pytest.MonkeyPatch) -> None:
    """The bearer must never follow a redirect to another host.

    `urlopen` forwards `Authorization` across a cross-host redirect, so a
    redirect is the one way this request could put the installation token in front
    of a third party. The response URL is compared against what was requested.
    """

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def geturl(self) -> str:
            return "https://elsewhere.example/steal"

        def read(self) -> bytes:
            return b"[]"

    monkeypatch.setattr(mint.urllib.request, "urlopen", lambda *_a, **_k: _Response())
    monkeypatch.setattr(mint, "API", "https://api.github.test")

    with pytest.raises(mint.MintError, match="refused a redirect"):
        mint._api("GET", "/repos/digithings-ai/digithings/branches/develop/protection", token=TOKEN)


def test_every_request_declares_a_timeout(monkeypatch: pytest.MonkeyPatch) -> None:
    """A hung socket must not hang the probe.

    Without a timeout this blocks indefinitely, and a guard that never returns is
    indistinguishable from a guard that is passing.
    """
    seen: dict[str, object] = {}

    class _Response:
        def __enter__(self) -> "_Response":
            return self

        def __exit__(self, *_exc: object) -> None:
            return None

        def geturl(self) -> str:
            return f"{mint.API}/repos/digithings-ai/digithings/branches/develop/protection"

        def read(self) -> bytes:
            return b"{}"

    def _urlopen(request: object, timeout: object = None) -> _Response:
        seen["timeout"] = timeout
        return _Response()

    monkeypatch.setattr(mint.urllib.request, "urlopen", _urlopen)

    assert (
        mint._api("GET", "/repos/digithings-ai/digithings/branches/develop/protection", token=TOKEN)
        == {}
    )

    assert seen["timeout"] == mint.REQUEST_TIMEOUT_SECONDS
    assert mint.REQUEST_TIMEOUT_SECONDS > 0
