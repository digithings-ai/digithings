"""Caller identity from a verified Cloudflare Access token.

Why this module exists
----------------------
The platform's end-user identity is moving off Supabase Auth to Cloudflare
Access (Chris, 2026-10-11, answering DIG-2900): Google, GitHub and X sign-in
are served by Cloudflare, and we do not hold a password for any caller. So
nothing here accepts a credential. :func:`identity_from_claims` takes the
**claims of an already-verified** Access JWT and normalises them into an
:class:`AccessIdentity`; there is no password path and none may be added.

Signature verification lives where Cloudflare documents it: in the Worker
that fronts the service, against the account's key set at
``https://<team-name>.cloudflareaccess.com/cdn-cgi/access/certs``, matching
the JWT ``kid`` against ``public_certs`` (never the single ``public_cert``,
which an outdated cache can serve expired). That keeps this module free of a
JWT dependency and of any new Worker binding — which is why it takes claims
rather than a token, and why the caller must verify first.

What this replaces
------------------
``digiquant/supabase/migrations/107_ensure_personal_workspace.sql`` gave every
``auth.users`` insert its own personal workspace, through the
``handle_new_auth_user_workspace`` trigger. Cloudflare Access has no insert
event, so the same rule — one workspace per caller, created on first sight —
becomes :func:`resolve_workspace_binding` over an injected store.

Scope, deliberately narrow
--------------------------
This module holds no workspace model and no Supabase coupling, so it cannot
disagree with either the tenancy schema (``digiquant.dashboard.tenancy``) or a
future D1 one. *Where* binding rows live is not decided here: the store is a
:class:`WorkspaceBindingStore` Protocol, and the D1 schema (DIG-2891) and the
cutover (DIG-2902 / DIG-2903) own that choice. Bindings are keyed on
``subject``, not ``email``: an Access subject is stable per IdP account while
an email address can change or be reused.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime, timezone
from typing import Any, Protocol

from pydantic import BaseModel, ConfigDict

# Score:allow untyped any — claim payloads are arbitrary decoded JSON.

#: Request header Cloudflare Access sets on requests it forwards.
ACCESS_JWT_HEADER = "cf-access-jwt-assertion"


class IdentityError(RuntimeError):
    """A claim set is not a usable, expected Access identity.

    The message always starts with a stable ``identity_error:<code>`` prefix so
    callers and log greps can key on the cause rather than on prose.
    """


class AccessIdentity(BaseModel):
    """One authenticated caller, as asserted by Cloudflare Access.

    Frozen: an identity is a fact about a request, not a mutable session.
    ``expires_at`` is timezone-aware (UTC) — the claim is an epoch second.
    """

    model_config = ConfigDict(frozen=True)

    subject: str
    email: str
    issuer: str
    audience: tuple[str, ...]
    expires_at: datetime


def _audiences(raw: Any) -> tuple[str, ...]:
    """Normalise the ``aud`` claim, which may be a string or a list of strings."""
    if isinstance(raw, str):
        return (raw,) if raw else ()
    if isinstance(raw, list):
        return tuple(item for item in raw if isinstance(item, str) and item)
    return ()


def identity_from_claims(
    claims: Mapping[str, Any],
    *,
    expected_issuer: str,
    expected_audience: str,
) -> AccessIdentity:
    """Build an :class:`AccessIdentity` from verified Access JWT claims.

    ``claims`` must already have had its signature verified by the caller
    (:data:`ACCESS_JWT_HEADER` is the header to read it from). This function is
    the remaining fail-closed boundary: it refuses any claim set that is not the
    issuer and audience the service expects, so a token minted for a different
    Access application cannot become an identity here.

    Raises :class:`IdentityError` with a stable code prefix on a missing or
    non-string ``sub``/``email``, an absent or unparseable ``exp``, an issuer
    that is not ``expected_issuer``, or an audience that does not contain
    ``expected_audience``.
    """
    if not isinstance(claims, Mapping):
        raise IdentityError("identity_error:claims_not_a_mapping")

    subject = claims.get("sub")
    if not isinstance(subject, str) or not subject:
        raise IdentityError("identity_error:subject_missing")

    email = claims.get("email")
    if not isinstance(email, str) or not email:
        raise IdentityError("identity_error:email_missing")

    issuer = claims.get("iss")
    if issuer != expected_issuer:
        raise IdentityError(f"identity_error:issuer_mismatch:{issuer!r}")

    audience = _audiences(claims.get("aud"))
    if expected_audience not in audience:
        raise IdentityError(f"identity_error:audience_mismatch:{audience!r}")

    exp = claims.get("exp")
    if isinstance(exp, bool) or not isinstance(exp, int | float):
        raise IdentityError("identity_error:exp_missing")

    return AccessIdentity(
        subject=subject,
        email=email,
        issuer=str(issuer),
        audience=audience,
        expires_at=datetime.fromtimestamp(float(exp), tz=timezone.utc),
    )


class WorkspaceBindingStore(Protocol):
    """Where a caller's workspace binding lives.

    Implemented by the tenancy store in use (Supabase during the rollback
    window, D1 after DIG-2891). Deliberately untyped on the row: the workspace
    model belongs to ``digiquant.dashboard.tenancy``, not here.
    """

    def find(self, subject: str) -> Mapping[str, Any] | None:  # score:allow untyped any
        """Return the existing binding for ``subject``, or ``None``."""
        ...

    def create(self, subject: str, email: str) -> Mapping[str, Any]:  # score:allow untyped any
        """Create and return the binding for a first-seen caller."""
        ...


def resolve_workspace_binding(
    identity: AccessIdentity,
    store: WorkspaceBindingStore,
) -> Mapping[str, Any]:  # score:allow untyped any
    """Return ``identity``'s workspace binding, creating it on first sight.

    This is the behaviour ``handle_new_auth_user_workspace`` gave an
    ``auth.users`` insert: exactly one workspace per caller, provisioned the
    first time the caller is seen and reused thereafter. Lookup is keyed on
    ``subject``.

    A ``create`` that returns ``None`` raises :class:`IdentityError` rather than
    handing back a binding that does not exist — the caller must not continue
    as if it had a workspace.
    """
    binding = store.find(identity.subject)
    if binding is not None:
        return binding

    created = store.create(identity.subject, identity.email)
    if created is None:
        raise IdentityError(f"identity_error:binding_not_created:{identity.subject}")
    return created
