"""Unit tests for the Cloudflare Access identity primitive.

Covers the two boundaries :mod:`digibase.identity` owns: turning verified
Access claims into an :class:`~digibase.identity.AccessIdentity`, and the
first-sight workspace binding that replaces ``handle_new_auth_user_workspace``.
"""

from __future__ import annotations

from typing import Any

import pytest
from digibase.identity import (
    ACCESS_JWT_HEADER,
    AccessIdentity,
    IdentityError,
    identity_from_claims,
    resolve_workspace_binding,
)
from pydantic import ValidationError

pytestmark = pytest.mark.unit

ISSUER = "https://digithings.cloudflareaccess.com"
AUD = "4714c1358e65fe4b408ad6d432a5f878f08194bdb4752441fd56faefa9b2b6f2"
SUBJECT = "1a2b3c4d-access-subject"
EMAIL = "operator@digithings.ai"
EXP = 1_792_000_000


def claims(**overrides: Any) -> dict[str, Any]:  # score:allow untyped any
    """A claim set that verifies — every rejection test perturbs exactly one key."""
    base: dict[str, Any] = {  # score:allow untyped any
        "sub": SUBJECT,
        "email": EMAIL,
        "iss": ISSUER,
        "aud": AUD,
        "exp": EXP,
    }
    base.update(overrides)
    return base


def test_access_jwt_header_is_the_documented_one() -> None:
    """The header Cloudflare Access sets is pinned, not left to a caller to know."""
    assert ACCESS_JWT_HEADER == "cf-access-jwt-assertion"


def test_identity_from_claims_returns_the_asserted_caller() -> None:
    """Positive control: a matching claim set yields the identity it asserts.

    This is the arm that makes every rejection below meaningful — a suite that
    only asserted "no exception" could not tell a working parse from one that
    rejected everything.
    """
    identity = identity_from_claims(claims(), expected_issuer=ISSUER, expected_audience=AUD)
    assert identity.subject == SUBJECT
    assert identity.email == EMAIL
    assert identity.issuer == ISSUER
    assert identity.audience == (AUD,)


def test_identity_from_claims_accepts_a_list_audience() -> None:
    """Access may send several audiences; the expected one must be among them."""
    identity = identity_from_claims(
        claims(aud=["other-application", AUD]),
        expected_issuer=ISSUER,
        expected_audience=AUD,
    )
    assert identity.audience == ("other-application", AUD)


def test_expiry_is_timezone_aware() -> None:
    """``exp`` is an epoch second and must land as aware UTC, not naive."""
    from datetime import timezone

    identity = identity_from_claims(claims(), expected_issuer=ISSUER, expected_audience=AUD)
    assert identity.expires_at.tzinfo is timezone.utc
    assert identity.expires_at.timestamp() == pytest.approx(EXP)


def test_identity_is_immutable() -> None:
    """An identity is a fact about one request, not a session to mutate."""
    identity = identity_from_claims(claims(), expected_issuer=ISSUER, expected_audience=AUD)
    with pytest.raises(ValidationError):
        identity.subject = "someone-else"  # type: ignore[misc]


class RecordingStore:
    """Workspace store that records every call, so "did not create" is measurable."""

    def __init__(
        self, existing: dict[str, dict[str, Any]] | None = None
    ) -> None:  # score:allow untyped any
        self.rows: dict[str, dict[str, Any]] = dict(existing or {})  # score:allow untyped any
        self.calls: list[str] = []
        self.create_result: Any = "created"  # score:allow untyped any

    def find(self, subject: str) -> dict[str, Any] | None:  # score:allow untyped any
        self.calls.append(f"find:{subject}")
        return self.rows.get(subject)

    def create(self, subject: str, email: str) -> Any:  # score:allow untyped any
        self.calls.append(f"create:{subject}:{email}")
        row = {"workspace_id": f"ws-{subject}", "subject": subject, "email": email}
        self.rows[subject] = row
        return None if self.create_result is None else row


def an_identity(**overrides: Any) -> AccessIdentity:  # score:allow untyped any
    return identity_from_claims(claims(**overrides), expected_issuer=ISSUER, expected_audience=AUD)


def test_first_sight_creates_the_binding() -> None:
    """A caller with no binding gets one — the trigger's behaviour, per request."""
    store = RecordingStore()
    binding = resolve_workspace_binding(an_identity(), store)
    assert binding["workspace_id"] == f"ws-{SUBJECT}"
    assert store.calls == [f"find:{SUBJECT}", f"create:{SUBJECT}:{EMAIL}"]


def test_second_sight_reuses_the_binding_without_creating() -> None:
    """The lookup arm must actually skip ``create``; a ``None`` check alone would pass either way."""
    store = RecordingStore()
    first = resolve_workspace_binding(an_identity(), store)
    second = resolve_workspace_binding(an_identity(), store)
    assert second == first
    assert store.calls.count(f"create:{SUBJECT}:{EMAIL}") == 1
    assert store.calls[-1] == f"find:{SUBJECT}"


def test_binding_is_keyed_on_subject_not_email() -> None:
    """Email can change or be reused, so it must not be the binding key."""
    store = RecordingStore()
    resolve_workspace_binding(an_identity(), store)
    other = resolve_workspace_binding(an_identity(sub="different-subject-same-email"), store)
    assert other["workspace_id"] == "ws-different-subject-same-email"
    assert sorted(store.rows) == sorted([SUBJECT, "different-subject-same-email"])


def test_create_returning_none_fails_closed() -> None:
    """A binding that was not written must not be handed back as if it existed."""
    store = RecordingStore()
    store.create_result = None
    with pytest.raises(IdentityError, match="binding_not_created"):
        resolve_workspace_binding(an_identity(), store)


@pytest.mark.parametrize(
    ("overrides", "code"),
    [
        ({"sub": ""}, "subject_missing"),
        ({"sub": 42}, "subject_missing"),
        ({"sub": None}, "subject_missing"),
        ({"email": ""}, "email_missing"),
        ({"email": None}, "email_missing"),
        ({"iss": "https://other-team.cloudflareaccess.com"}, "issuer_mismatch"),
        ({"iss": None}, "issuer_mismatch"),
        ({"aud": "another-applications-aud"}, "audience_mismatch"),
        ({"aud": []}, "audience_mismatch"),
        ({"aud": None}, "audience_mismatch"),
        ({"exp": "soon"}, "exp_missing"),
        ({"exp": None}, "exp_missing"),
        ({"exp": True}, "exp_missing"),
    ],
)
def test_identity_from_claims_refuses(overrides: dict[str, Any], code: str) -> None:
    """Each defect refuses with its own stable code, so the cause survives into logs."""
    with pytest.raises(IdentityError) as excinfo:
        identity_from_claims(claims(**overrides), expected_issuer=ISSUER, expected_audience=AUD)
    # Code is the stable segment; some errors append a detail segment after it.
    assert str(excinfo.value).split(":")[1] == code


def test_identity_from_claims_refuses_a_non_mapping() -> None:
    """A non-mapping payload is refused, not indexed into."""
    with pytest.raises(IdentityError, match="identity_error:claims_not_a_mapping"):
        identity_from_claims(
            ["sub", SUBJECT],  # type: ignore[arg-type]
            expected_issuer=ISSUER,
            expected_audience=AUD,
        )


def test_a_token_for_another_access_application_is_refused() -> None:
    """A correctly signed token minted for another Access app must not authenticate here."""
    with pytest.raises(IdentityError, match="identity_error:audience_mismatch"):
        identity_from_claims(
            claims(aud="some-other-zero-trust-application"),
            expected_issuer=ISSUER,
            expected_audience=AUD,
        )


def test_a_token_from_another_team_is_refused() -> None:
    """Issuer is checked too, so a valid signature from another account is not enough."""
    with pytest.raises(IdentityError, match="identity_error:issuer_mismatch"):
        identity_from_claims(
            claims(iss="https://attacker.cloudflareaccess.com"),
            expected_issuer=ISSUER,
            expected_audience=AUD,
        )
