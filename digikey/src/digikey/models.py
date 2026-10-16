"""Pydantic models for JWT claims and request auth context."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

PrincipalKind = Literal["api_key", "bff_session", "legacy_static"]


class TokenClaims(BaseModel):
    """Normalized claims after JWT verification (custom + registered)."""

    sub: str
    iss: str
    aud: str | list[str]
    exp: int | None = None
    jti: str | None = None
    tenant_slug: str = ""
    tenant_id: str | None = None
    project_id: str | None = None
    project_config_ref: str | None = None
    profile_id: str | None = Field(
        default=None,
        description="Optional user profile pointer (#308); absent when no profile yet.",
    )
    profile_version: int | None = Field(
        default=None,
        description="Monotonic profile revision; paired with profile_id when present.",
    )
    scopes: list[str] = Field(default_factory=list)
    key_pub: str | None = Field(default=None, description="Public key prefix only")
    principal_kind: PrincipalKind = "api_key"
    legacy_static: bool = False
    raw: dict[str, Any] = Field(default_factory=dict, repr=False)


class DigiAuthContext(BaseModel):
    """Attached to FastAPI request.state after successful auth."""

    subject: str
    tenant_slug: str = ""
    tenant_slug_verified: bool = False
    """True only when tenant_slug came from the decoded, signature-verified JWT
    claim. False when empty, or when filled in from the unsigned X-Digi-Tenant /
    X-Digichat-Tenant header fallback (see service_middleware.jwt_context).
    Consumers doing real tenant *authorization* (not just routing/logging) must
    check this before trusting tenant_slug. See #2303."""
    project_id: str | None = None
    project_config_ref: str | None = None
    profile_id: str | None = None
    profile_version: int | None = None
    scopes: list[str] = Field(default_factory=list)
    key_prefix: str | None = None
    jti: str | None = None
    principal_kind: PrincipalKind = "api_key"
    legacy_static: bool = False
    bearer_token: str | None = Field(
        default=None,
        repr=False,
        description="Raw JWT for outbound forwarding; never log.",
    )
    caller_service: str | None = None


def claims_to_context(claims: TokenClaims, *, bearer_token: str | None) -> DigiAuthContext:
    return DigiAuthContext(
        subject=claims.sub,
        tenant_slug=claims.tenant_slug,
        tenant_slug_verified=bool(claims.tenant_slug),
        project_id=claims.project_id,
        project_config_ref=claims.project_config_ref,
        profile_id=claims.profile_id,
        profile_version=claims.profile_version,
        scopes=list(claims.scopes),
        key_prefix=claims.key_pub,
        jti=claims.jti,
        principal_kind=claims.principal_kind,
        legacy_static=claims.legacy_static,
        bearer_token=bearer_token,
    )
