"""DigiKey FastAPI service."""

from __future__ import annotations

import logging
import os
import secrets
import time
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select

from digibase.cors import install_cors
from digibase.errors import register_fastapi_error_handlers
from digibase.http import install_request_id_logging, install_request_id_middleware
from digibase.metrics import install_metrics

from digikey import __version__, blocklist
from digikey.crypto_keys import load_or_create_signing_key
from digikey.db import init_db, session_factory
from digikey.db_schema import ApiKeyRow, JtiIssuedRow, utcnow
from digikey.jwt_issue import issue_access_token, public_jwks
from digikey.key_crypto import generate_raw_key, hash_secret, verify_secret
from digikey.ratelimit import rate_limit_dependency, register_rate_limit_handler
from digikey.scopes import DEFAULT_BFF_SESSION_SCOPES, scope_grants_required
from digikey.settings import KEY_PREFIX_LEN, admin_token, allow_dev_global_keys, bff_token

logger = logging.getLogger(__name__)

app = FastAPI(title="DigiKey", version=__version__)
register_rate_limit_handler(app)
install_metrics(app, service="digikey", version=__version__)
install_cors(app, service="digikey")
install_request_id_middleware(app)
install_request_id_logging()

_private_key, _kid = load_or_create_signing_key()


@app.on_event("startup")
def _startup() -> None:
    init_db()
    if not admin_token():
        logger.warning("DIGIKEY_ADMIN_TOKEN is unset — POST /v1/admin/keys returns 503")
    if not blocklist.is_configured():
        logger.warning(
            "DIGIKEY_BLOCKLIST_REDIS_URL is unset — JWT revocation blocklist disabled "
            "(tokens issued before revoke_at will remain valid until exp)",
        )
    if not (os.environ.get("DIGIKEY_PRIVATE_KEY_PEM") or "").strip():
        if os.environ.get("DIGIKEY_ALLOW_EPHEMERAL_KEY", "0").strip().lower() in (
            "1",
            "true",
            "yes",
        ):
            logger.warning(
                "DIGIKEY_ALLOW_EPHEMERAL_KEY=1: ephemeral signing key; set DIGIKEY_PRIVATE_KEY_PEM "
                "for stable JWKS across restarts",
            )


@app.get("/health")
def health() -> dict[str, str]:
    """Legacy health check (kept for back-compat)."""
    return {"status": "ok", "service": "digikey"}


@app.get("/healthz")
def healthz() -> dict[str, bool]:
    """Minimal liveness probe. Auth-exempt, rate-limit-exempt, secret-free.

    Returns HTTP 200 with ``{"ok": true}``. Intended for load-balancer and
    k8s liveness checks. For richer cross-service diagnostics, call DigiSmith's
    ``/v1/status``.
    """
    return {"ok": True}


@app.get("/.well-known/jwks.json")
def jwks() -> dict[str, Any]:
    return public_jwks(_private_key, _kid)


def _require_admin(request: Request) -> None:
    tok = admin_token()
    if not tok:
        raise HTTPException(status_code=503, detail="DIGIKEY_ADMIN_TOKEN not configured")
    auth = request.headers.get("Authorization") or ""
    if not secrets.compare_digest(auth, f"Bearer {tok}"):
        raise HTTPException(status_code=401, detail="admin unauthorized")


class AdminIssueBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    tenant_slug: str = Field(..., min_length=1, max_length=256)
    label: str | None = Field(default=None, max_length=256)
    scopes: list[str] = Field(default_factory=list)
    kind: str = Field(default="standard", pattern="^(standard|dev_global)$")
    project_id: str | None = None
    project_config_ref: str | None = None


class AdminIssueResponse(BaseModel):
    key_prefix: str
    api_key: str
    id: str


@app.post(
    "/v1/admin/keys",
    response_model=AdminIssueResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
def admin_issue_key(body: AdminIssueBody, request: Request) -> AdminIssueResponse:
    _require_admin(request)
    if body.kind == "dev_global" and not allow_dev_global_keys():
        raise HTTPException(
            status_code=403, detail="dev_global keys disabled (set DIGIKEY_ALLOW_DEV_GLOBAL=1)"
        )
    raw, prefix = generate_raw_key()
    scopes = body.scopes
    if body.kind == "dev_global" and (not scopes or scopes == ["*"]):
        scopes = ["*"]
    row = ApiKeyRow(
        key_hash=hash_secret(raw),
        key_prefix=prefix,
        tenant_slug=body.tenant_slug.strip(),
        project_id=(body.project_id or "").strip() or None,
        project_config_ref=(body.project_config_ref or "").strip() or None,
        scopes=scopes,
        kind=body.kind,
        label=body.label,
    )
    sf = session_factory()
    with sf() as session:
        session.add(row)
        session.commit()
        session.refresh(row)
        rid = row.id
    return AdminIssueResponse(key_prefix=prefix, api_key=raw, id=rid)


class TokenRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    grant_type: str = Field(..., pattern="^(api_key|bff_session)$")
    api_key: str | None = None
    tenant_slug: str | None = None
    subject: str | None = None
    project_id: str | None = None
    project_config_ref: str | None = None
    audience: str | None = None
    requested_scopes: list[str] | None = None


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"
    expires_in: int
    #: When set via DIGIKEY_LITELLM_PROXY_KEY, clients use this Bearer to LiteLLM (same as LITELLM_MASTER_KEY in dev).
    litellm_proxy_api_key: str | None = None


def _jwt_ttl() -> int:
    return int(os.environ.get("DIGIKEY_JWT_TTL_SEC") or "900")


@app.post(
    "/v1/oauth/token",
    response_model=TokenResponse,
    response_model_exclude_none=True,
    dependencies=[Depends(rate_limit_dependency)],
)
def oauth_token(body: TokenRequest, request: Request) -> TokenResponse:
    ttl = _jwt_ttl()
    if body.grant_type == "bff_session":
        btok = bff_token()
        if not btok:
            raise HTTPException(
                status_code=503, detail="bff_session grant not configured (DIGIKEY_BFF_TOKEN)"
            )
        auth = request.headers.get("Authorization") or ""
        if not secrets.compare_digest(auth, f"Bearer {btok}"):
            raise HTTPException(status_code=401, detail="bff unauthorized")
        if not body.tenant_slug or not body.subject:
            raise HTTPException(status_code=400, detail="tenant_slug and subject required")
        scopes = list(DEFAULT_BFF_SESSION_SCOPES)
        if body.requested_scopes:
            if not scope_grants_required(scopes, body.requested_scopes):
                raise HTTPException(
                    status_code=400, detail="requested_scopes not allowed for bff session"
                )
            scopes = body.requested_scopes
        token, _jti = issue_access_token(
            _private_key,
            kid=_kid,
            sub=f"bff:{body.subject}",
            tenant_slug=body.tenant_slug.strip(),
            scopes=scopes,
            key_pub=None,
            project_id=(body.project_id or "").strip() or None,
            project_config_ref=(body.project_config_ref or "").strip() or None,
            principal_kind="bff_session",
            audience=body.audience,
            ttl_sec=ttl,
        )
        llm_key = (os.environ.get("DIGIKEY_LITELLM_PROXY_KEY") or "").strip() or None
        return TokenResponse(access_token=token, expires_in=ttl, litellm_proxy_api_key=llm_key)

    if not body.api_key:
        raise HTTPException(status_code=400, detail="api_key required")
    raw = body.api_key.strip()
    prefix = raw[:KEY_PREFIX_LEN]
    sf = session_factory()
    with sf() as session:
        rows = list(session.scalars(select(ApiKeyRow).where(ApiKeyRow.key_prefix == prefix)))
        row: ApiKeyRow | None = None
        for r in rows:
            if verify_secret(raw, r.key_hash):
                row = r
                break
        if row is None:
            raise HTTPException(status_code=401, detail="invalid api_key")
        if row.revoked_at is not None:
            raise HTTPException(status_code=401, detail="key revoked")
        if row.kind == "dev_global" and not allow_dev_global_keys():
            raise HTTPException(status_code=403, detail="dev_global exchange disabled")

        scopes = list(row.scopes) if isinstance(row.scopes, list) else []
        if body.requested_scopes:
            if not scope_grants_required(scopes, body.requested_scopes):
                raise HTTPException(
                    status_code=400, detail="requested_scopes not allowed for this key"
                )
            scopes = body.requested_scopes

        token, jti = issue_access_token(
            _private_key,
            kid=_kid,
            sub=f"key:{row.id}",
            tenant_slug=row.tenant_slug,
            scopes=scopes,
            key_pub=row.key_prefix,
            project_id=row.project_id,
            project_config_ref=row.project_config_ref,
            principal_kind="api_key",
            audience=body.audience,
            ttl_sec=ttl,
        )
        # An untracked jti can never be revoked, so refuse to emit the token
        # if the durable record can't be written. See ADR-0007.
        try:
            session.add(JtiIssuedRow(jti=jti, api_key_id=row.id, exp=int(time.time()) + ttl))
            session.commit()
        except Exception as e:
            session.rollback()
            logger.error("jti_issued insert failed; refusing to issue token: %s", e)
            raise HTTPException(status_code=503, detail="token issuance unavailable") from e
    llm_key = (os.environ.get("DIGIKEY_LITELLM_PROXY_KEY") or "").strip() or None
    return TokenResponse(access_token=token, expires_in=ttl, litellm_proxy_api_key=llm_key)


class RevokeResponse(BaseModel):
    revoked: bool
    jtis_invalidated: int


@app.post(
    "/v1/admin/keys/{key_id}/revoke",
    response_model=RevokeResponse,
    dependencies=[Depends(rate_limit_dependency)],
)
def admin_revoke_key(key_id: str, request: Request) -> RevokeResponse:
    """Revoke a key and blocklist all live JWTs issued from it (ADR-0007)."""
    _require_admin(request)
    sf = session_factory()
    now_ts = int(time.time())
    with sf() as session:
        row = session.get(ApiKeyRow, key_id)
        if row is None:
            raise HTTPException(status_code=404, detail="key not found")
        if row.revoked_at is None:
            row.revoked_at = utcnow()
        live = list(
            session.scalars(
                select(JtiIssuedRow).where(
                    JtiIssuedRow.api_key_id == key_id,
                    JtiIssuedRow.exp > now_ts,
                )
            )
        )
        entries = [(r.jti, r.exp - now_ts) for r in live]
        try:
            written = blocklist.write_blocklist_bulk(entries)
        except blocklist.BlocklistUnavailable as e:
            # If we can't guarantee every live JWT is blocked, don't mark the
            # key revoked — otherwise ``revoked_at`` would suggest closure
            # the blocklist hasn't actually delivered. Caller retries on 503.
            session.rollback()
            logger.error("revoke blocklist write failed: %s", e)
            raise HTTPException(status_code=503, detail="auth_backend_unavailable") from e
        session.commit()
    return RevokeResponse(revoked=True, jtis_invalidated=written)


register_fastapi_error_handlers(app, service="digikey")
