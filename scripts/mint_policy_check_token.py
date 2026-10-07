#!/usr/bin/env python3
"""Mint and smoke-test the ``policy-check-reader`` GitHub App token (DIG-2102).

The planned drift guard, ``scripts/check_required_policy_checks.py --live``
(DIG-2098 decision D), cannot read branch protection with a workflow's own
``GITHUB_TOKEN``: the endpoint needs ``Administration: read``, and that
permission has no key in the ``permissions:`` vocabulary of an Actions
installation token. Comparing the committed policy inventory against the *real*
required set therefore needs one non-human credential that can hold it — the App
documented in ``docs/ops/policy-check-credential.md``.

This script is the **local half** of that credential. It signs the App JWT with
the App private key, exchanges it for an installation token, and with ``--verify``
performs the one read the guard actually needs, so a rotation can be proved
*before* the old key is deleted. A scheduled guard run mints in Actions instead
(``actions/create-github-app-token``, to be pinned by SHA); both mint the same
thing from the same key.

**Never prints the token or the key.** It reports the token's expiry and, under
``--verify``, the required contexts it read. The private key is read from the
environment or a file and is deliberately *not* accepted as an argv value, because
argv is world-readable in ``ps``.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import time
import urllib.error
import urllib.request
from typing import Any

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding, rsa

API = "https://api.github.com"
DEFAULT_REPO = "digithings-ai/digithings"
DEFAULT_BRANCH = "develop"

APP_ID_ENV = "POLICY_CHECK_APP_ID"
INSTALLATION_ID_ENV = "POLICY_CHECK_INSTALLATION_ID"
PRIVATE_KEY_ENV = "POLICY_CHECK_APP_PRIVATE_KEY"
PRIVATE_KEY_FILE_FLAG = "--private-key-file"

# GitHub caps an App JWT at 10 minutes. Mint close to that ceiling so the window
# between "signed" and "exchanged" is small, then backdate 60s so a runner whose
# clock trails the API's still authenticates.
JWT_TTL_SECONDS = 540
JWT_CLOCK_SKEW_SECONDS = 60

OK = 0
FAILED = 1
SETUP_ERROR = 2

# Without a timeout a runner that accepts the connection and never answers hangs
# until the Actions 6-hour ceiling, which reads as a pipeline timeout rather than
# as anything about the credential.
REQUEST_TIMEOUT_SECONDS = 30

USER_AGENT = "digithings-policy-check-reader"


class MintError(RuntimeError):
    """The credential could not be proven usable. Never carries secret material."""


class ApiError(MintError):
    """GitHub answered with an error status — the only outcome that proves anything.

    Everything else this script can hit is indistinguishable from a broken setup: a
    missing id, an unreadable/encrypted/malformed PEM, a DNS blip, or a body that is
    not JSON. Those are ``SETUP_ERROR``. This one is ``FAILED``, because GitHub
    looked and said no.
    """


# Anything fixable by the operator before GitHub has answered. None of it proves the
# credential is wrong, so none of it may exit FAILED — during a rotation the operator
# deletes the previous key only once this script proves the new one works, and
# "I could not tell" must not read as "the new key is bad".
SETUP_ERRORS = (MintError, ValueError, TypeError, OSError, urllib.error.URLError)


def _b64(raw: bytes) -> str:
    """Base64url without padding, per JWT."""
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


def _json_segment(payload: dict[str, Any]) -> str:
    return _b64(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))


def build_jwt(
    app_id: str,
    key_pem: bytes,
    *,
    now: int | None = None,
    ttl: int = JWT_TTL_SECONDS,
) -> str:
    """Return the RS256 JWT that authenticates *us as the App*, not as a user.

    ``alg`` is pinned here rather than taken from any input, so no caller can turn
    this into an ``alg: none`` or an HMAC-signed forgery. ``ttl`` is capped for the
    same reason: GitHub rejects an App JWT older than 10 minutes, so a caller must
    not be able to mint one that looks fine and then fails at the exchange.
    """
    ttl = min(ttl, JWT_TTL_SECONDS)
    issued = int(time.time()) if now is None else now
    signing_input = (
        _json_segment({"alg": "RS256", "typ": "JWT"})
        + "."
        + _json_segment(
            {
                "iat": issued - JWT_CLOCK_SKEW_SECONDS,
                "exp": issued + ttl,
                "iss": app_id,
            }
        )
    )
    key = serialization.load_pem_private_key(key_pem, password=None)
    if not isinstance(key, rsa.RSAPrivateKey):
        raise MintError(f"App private key is a {type(key).__name__}, not an RSA key")
    signature = key.sign(signing_input.encode("ascii"), padding.PKCS1v15(), hashes.SHA256())
    return signing_input + "." + _b64(signature)


def _api(
    method: str,
    path: str,
    *,
    token: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """One GitHub REST call. Fixed ``https`` host, so no URL is assembled from input."""
    body = None if payload is None else json.dumps(payload).encode("utf-8")
    headers = {
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": USER_AGENT,
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    request = urllib.request.Request(
        f"{API}{path}",
        data=body,
        method=method,
        headers=headers,
    )
    try:
        with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT_SECONDS) as response:
            # urllib's redirect handler forwards every header except content-length and
            # content-type, so a cross-host 30x would hand the bearer token to that host
            # (and a https -> http one in cleartext). api.github.com does not redirect
            # these paths, but this is the one script here whose whole job is holding a
            # credential, so refuse to follow one rather than reason about it.
            final_url = response.geturl()
            if final_url != f"{API}{path}":
                raise MintError(f"{method} {path} -> refused a redirect to {final_url}")
            return json.loads(response.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        # Deliberately not echoing the response body: for a 403 it can echo the
        # request headers, which carry the credential. This is the one failure that
        # proves the credential is wrong rather than merely untested.
        raise ApiError(f"{method} {path} -> HTTP {exc.code} {exc.reason}") from None


def mint_token(jwt: str, installation_id: str) -> tuple[str, str]:
    """Exchange an App JWT for an installation token. Returns ``(token, expires_at)``.

    The token lives in the return value and nowhere else: it is never logged and
    never written to disk.
    """
    data = _api(
        "POST",
        f"/app/installations/{installation_id}/access_tokens",
        token=jwt,
    )
    token = data.get("token")
    if not isinstance(token, str) or not token:
        raise MintError("mint response carried no token")
    return token, str(data.get("expires_at", "unknown"))


def read_required_contexts(token: str, repo: str, branch: str) -> list[str]:
    """The read the drift guard exists to perform. Raises if the grant is missing."""
    data = _api(
        "GET",
        f"/repos/{repo}/branches/{branch}/protection/required_status_checks",
        token=token,
    )
    contexts = data.get("contexts")
    return list(contexts) if isinstance(contexts, list) else []


def _load_key(args: argparse.Namespace) -> bytes:
    """Read the App private key. Always bytes, because the PEM parser requires it."""
    if args.private_key_file:
        try:
            with open(args.private_key_file, encoding="utf-8") as handle:
                return handle.read().encode("utf-8")
        except OSError as exc:
            raise MintError(f"cannot read {args.private_key_file}: {exc.strerror}") from None
    raw = os.environ.get(PRIVATE_KEY_ENV, "")
    if raw:
        return raw.encode("utf-8")
    raise MintError(f"no App private key: export {PRIVATE_KEY_ENV} or pass {PRIVATE_KEY_FILE_FLAG}")


def _parser() -> argparse.ArgumentParser:
    # allow_abbrev=False is load-bearing, not tidiness: with abbreviations on,
    # argparse matches `--private-key` as an unambiguous prefix of
    # `--private-key-file`, so an operator passing a PEM as a flag value would be
    # accepted and the secret would land in argv, where `ps` shows it to every
    # process on the runner.
    parser = argparse.ArgumentParser(
        description=(
            "Mint a policy-check-reader installation token and, with --verify, prove it "
            "can read branch protection. Never prints the token."
        ),
        allow_abbrev=False,
    )
    parser.add_argument(
        "--app-id",
        default=os.environ.get(APP_ID_ENV),
        help=f"App id (default: ${APP_ID_ENV})",
    )
    parser.add_argument(
        "--installation-id",
        default=os.environ.get(INSTALLATION_ID_ENV),
        help=f"Installation id (default: ${INSTALLATION_ID_ENV})",
    )
    parser.add_argument(
        PRIVATE_KEY_FILE_FLAG,
        help=(
            "PEM file holding the App private key. Omit and export "
            f"${PRIVATE_KEY_ENV} instead. Deliberately not accepted as an argv "
            "value: argv is readable by any process in `ps`."
        ),
    )
    parser.add_argument(
        "--repo", default=DEFAULT_REPO, help=f"owner/name (default: {DEFAULT_REPO})"
    )
    parser.add_argument(
        "--branch", default=DEFAULT_BRANCH, help=f"branch to read (default: {DEFAULT_BRANCH})"
    )
    parser.add_argument(
        "--verify",
        action="store_true",
        help="Read the branch's required status-check contexts with the minted token.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)

    try:
        if not args.app_id:
            raise MintError(f"no App id: pass --app-id or export {APP_ID_ENV}")
        if not args.installation_id:
            raise MintError(
                f"no installation id: pass --installation-id or export {INSTALLATION_ID_ENV}"
            )
        token, expires_at = mint_token(
            build_jwt(args.app_id, _load_key(args)),
            args.installation_id,
        )
    except ApiError as exc:
        # GitHub rejected the JWT: the key is wrong, revoked, or not this App's.
        print(f"FAIL mint: {exc}", file=sys.stderr)
        print(
            "The App private key did not authenticate. Do not delete a working key.",
            file=sys.stderr,
        )
        return FAILED
    except SETUP_ERRORS as exc:
        print(f"FAIL mint: {exc}", file=sys.stderr)
        print(
            "Setup could not be completed, so nothing is proven about the credential "
            "itself — check the id variables and the key export before reading this as a "
            "key problem.",
            file=sys.stderr,
        )
        return SETUP_ERROR

    # Past this line the token exists only in memory, and only as a bearer header.
    print(f"OK mint: installation token valid, expires {expires_at}")

    if not args.verify:
        return OK

    try:
        contexts = read_required_contexts(token, args.repo, args.branch)
    except ApiError as exc:
        print(f"FAIL verify: {exc}", file=sys.stderr)
        print(
            "The key minted a token, so it is valid — but the Administration: read "
            "grant is missing or scoped to another repository.",
            file=sys.stderr,
        )
        return FAILED
    except SETUP_ERRORS as exc:
        # Same distinction as above, and the reason it matters: the guard's failure
        # mode is a stale snapshot, so a transport blip must never be filed as one.
        print(f"FAIL verify: {exc}", file=sys.stderr)
        print(
            "The read did not complete, so the branch's required set is unverified — "
            "this is not evidence that the snapshot is stale.",
            file=sys.stderr,
        )
        return SETUP_ERROR

    print(f"OK verify: {args.repo}@{args.branch} requires {len(contexts)} context(s)")
    for context in contexts:
        print(f"  - {context}")
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
