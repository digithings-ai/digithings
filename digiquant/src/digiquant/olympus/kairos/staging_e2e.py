"""Kairos staging E2E runner — Observer hops, then remaining-hop product state.

Phase A: Settings/checkout probes without vendor secrets. Observer writes
must return ``TIER_FORBIDDEN``. Checkout may still be a named config miss.

Phase A2: Settings GETs (profile billing, brokers, jobs, fills, digest log).
Exit 0 only when all five remaining hops are proven from that product state.

Phase B: named vendor secrets. Missing → exit 2 (never paper-fakes).

Phase C: checkout URL + webhook past ``STRIPE_NOT_CONFIGURED`` → exit 4
with named remaining hops still unproven.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Callable, Mapping
from enum import StrEnum
from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.kairos.remaining_hops import (
    EXIT_REMAINING_HOPS_UNPROVEN,
    REMAINING_LIVE_HOPS,
    RemainingHopEvidence,
    format_remaining_hops_failure,
    proven_remaining_hops,
    remaining_hops_unproven,
)
from digiquant.olympus.kairos.staging_secrets import (
    KAIROS_STAGING_REQUIRED_SECRETS,
    format_missing_secrets_failure,
    missing_kairos_staging_secrets,
)

DEFAULT_FUNCTIONS_BASE = "https://rwagjbkvxkdwqmouagad.supabase.co/functions/v1"
DEFAULT_SUPABASE_URL = "https://rwagjbkvxkdwqmouagad.supabase.co"
CHECKOUT_CONFIG_MISS_CODES: frozenset[str] = frozenset(
    {
        "PRICE_NOT_CONFIGURED",
        "STRIPE_NOT_CONFIGURED",
        "APP_URL_NOT_CONFIGURED",
    }
)

# Until each remaining hop is proven, the harness must not exit 0.


class HttpJson(Protocol):
    def __call__(
        self,
        method: str,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        body: dict[str, object] | None = None,
    ) -> tuple[int, dict[str, object]]: ...


class HopExpectation(StrEnum):
    """Closed vocabulary for Observer-phase assertions."""

    READ_OK = "read_ok"
    TIER_FORBIDDEN = "tier_forbidden"
    PRICE_OR_SESSION = "price_or_session"
    NOT_FOUND = "not_found"


class ObserverHop(BaseModel):
    """One Settings/checkout probe the Observer JWT must satisfy."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str = Field(..., min_length=1)
    method: Literal["GET", "POST", "PATCH"]
    path: str = Field(..., min_length=1)
    kind: HopExpectation
    body: dict[str, object] | None = None


class ProbeResult(BaseModel):
    """Sanitized hop outcome — codes only, never tokens."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    label: str
    http: int
    code: str | None = None
    ok: bool
    kind: HopExpectation


# Connect is POST /settings/brokers/connect — POST /settings/brokers is NOT_FOUND.
OBSERVER_HOPS: tuple[ObserverHop, ...] = (
    ObserverHop(
        label="GET /settings/profile",
        method="GET",
        path="/settings/profile",
        kind=HopExpectation.READ_OK,
    ),
    ObserverHop(
        label="GET /settings/notifications",
        method="GET",
        path="/settings/notifications",
        kind=HopExpectation.READ_OK,
    ),
    ObserverHop(
        label="GET /settings/brokers",
        method="GET",
        path="/settings/brokers",
        kind=HopExpectation.READ_OK,
    ),
    ObserverHop(
        label="GET /settings/keys", method="GET", path="/settings/keys", kind=HopExpectation.READ_OK
    ),
    ObserverHop(
        label="PATCH /settings/profile",
        method="PATCH",
        path="/settings/profile",
        kind=HopExpectation.TIER_FORBIDDEN,
        body={"profile_key": "workspace", "label": "probe"},
    ),
    ObserverHop(
        label="POST /settings/brokers/connect",
        method="POST",
        path="/settings/brokers/connect",
        kind=HopExpectation.TIER_FORBIDDEN,
        body={
            "broker": "alpaca",
            "env": "paper",
            "kind": "api_key",
        },
    ),
    ObserverHop(
        label="POST /settings/keys/connect",
        method="POST",
        path="/settings/keys/connect",
        kind=HopExpectation.TIER_FORBIDDEN,
        body={"provider": "openai", "kind": "api_key"},
    ),
    ObserverHop(
        label="POST /create-checkout-session",
        method="POST",
        path="/create-checkout-session",
        kind=HopExpectation.PRICE_OR_SESSION,
        body={"tier": "custom", "interval": "monthly"},
    ),
    ObserverHop(
        label="POST /settings/brokers (wrong path)",
        method="POST",
        path="/settings/brokers",
        kind=HopExpectation.NOT_FOUND,
        body={"broker": "alpaca", "env": "paper"},
    ),
)


def hop_ok(kind: HopExpectation, http: int, code: str | None) -> bool:
    """Return whether a live response matches the Observer-phase expectation."""
    if kind is HopExpectation.READ_OK:
        return http == 200
    if kind is HopExpectation.TIER_FORBIDDEN:
        return http == 403 and code == "TIER_FORBIDDEN"
    if kind is HopExpectation.PRICE_OR_SESSION:
        if http >= 500 and code in CHECKOUT_CONFIG_MISS_CODES:
            return True
        return http in {200, 201}
    if kind is HopExpectation.NOT_FOUND:
        return http == 404 and code == "NOT_FOUND"
    unhandled: HopExpectation = kind
    raise AssertionError(f"unhandled hop kind {unhandled}")


def _response_code(body: dict[str, object]) -> str | None:
    raw = body.get("code")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def run_observer_hops(
    *,
    http: HttpJson,
    jwt: str,
    anon_key: str | None,
    functions_base: str,
) -> list[ProbeResult]:
    """Probe Settings + checkout as an Observer JWT. Never logs the token."""
    headers: dict[str, str] = {"Authorization": f"Bearer {jwt}"}
    if anon_key:
        headers["apikey"] = anon_key
    base = functions_base.rstrip("/")
    results: list[ProbeResult] = []
    for hop in OBSERVER_HOPS:
        status, body = http(
            hop.method,
            f"{base}{hop.path}",
            headers=headers,
            body=hop.body,
        )
        code = _response_code(body)
        results.append(
            ProbeResult(
                label=hop.label,
                http=status,
                code=code,
                ok=hop_ok(hop.kind, status, code),
                kind=hop.kind,
            )
        )
    return results


def collect_remaining_evidence(
    *,
    http: HttpJson,
    jwt: str,
    anon_key: str | None,
    functions_base: str,
) -> RemainingHopEvidence:
    """GET Settings snapshots used to prove remaining hops. Never logs tokens."""
    headers: dict[str, str] = {"Authorization": f"Bearer {jwt}"}
    if anon_key:
        headers["apikey"] = anon_key
    base = functions_base.rstrip("/")

    def _get(path: str) -> dict[str, object]:
        status, body = http("GET", f"{base}{path}", headers=headers, body=None)
        if status != 200 or not isinstance(body, dict):
            return {}
        return body

    profile = _get("/settings/profile")
    brokers = _get("/settings/brokers")
    jobs_body = _get("/settings/jobs")
    fills_body = _get("/settings/fills")
    log_body = _get("/settings/notifications/log")
    connections: list[tuple[str, str, str]] = []
    raw_conns = brokers.get("connections")
    if isinstance(raw_conns, list):
        for row in raw_conns:
            if not isinstance(row, dict):
                continue
            connections.append(
                (
                    str(row.get("broker") or ""),
                    str(row.get("env") or ""),
                    str(row.get("status") or ""),
                )
            )
    jobs: list[tuple[str, str]] = []
    raw_jobs = jobs_body.get("jobs")
    if isinstance(raw_jobs, list):
        for row in raw_jobs:
            if not isinstance(row, dict):
                continue
            jobs.append((str(row.get("job_type") or ""), str(row.get("status") or "")))
    fills = fills_body.get("fills")
    fill_count = len(fills) if isinstance(fills, list) else 0
    keys: list[str] = []
    raw_events = log_body.get("events")
    if isinstance(raw_events, list):
        for row in raw_events:
            if isinstance(row, dict) and isinstance(row.get("event_key"), str):
                keys.append(str(row["event_key"]))
    sub = profile.get("subscription_status")
    return RemainingHopEvidence(
        subscription_status=str(sub) if isinstance(sub, str) else None,
        connections=tuple(connections),
        jobs=tuple(jobs),
        fill_count=fill_count,
        digest_event_keys=tuple(keys),
    )


class JwtResolution(BaseModel):
    """JWT lookup outcome — never includes the token in logs (caller must not)."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    token: str | None = None
    attempted_grant: bool = False
    grant_http: int | None = None


def password_grant_access_token(
    *,
    http: HttpJson,
    supabase_url: str,
    anon_key: str,
    email: str,
    password: str,
) -> tuple[str | None, int]:
    """Exchange email/password for an access token. Returns (token, http)."""
    status, body = http(
        "POST",
        f"{supabase_url.rstrip('/')}/auth/v1/token?grant_type=password",
        headers={"apikey": anon_key, "Content-Type": "application/json"},
        body={"email": email, "password": password},
    )
    if status != 200:
        return None, status
    token = body.get("access_token")
    if not isinstance(token, str) or not token.strip():
        return None, status
    return token.strip(), status


def resolve_staging_jwt(*, http: HttpJson, environ: Mapping[str, str]) -> JwtResolution:
    """JWT from env, or password grant when email/password/anon are set."""
    direct = (environ.get("KAIROS_STAGING_USER_JWT") or "").strip()
    if direct:
        return JwtResolution(token=direct)
    email = (environ.get("KAIROS_STAGING_EMAIL") or "").strip()
    password = (environ.get("KAIROS_STAGING_PASSWORD") or "").strip()
    anon = _anon_from_env(environ)
    supabase_url = (environ.get("CORE_SUPABASE_URL") or DEFAULT_SUPABASE_URL).strip()
    if not (email and password and anon):
        return JwtResolution()
    token, grant_http = password_grant_access_token(
        http=http,
        supabase_url=supabase_url,
        anon_key=anon,
        email=email,
        password=password,
    )
    return JwtResolution(token=token, attempted_grant=True, grant_http=grant_http)


def _anon_from_env(environ: Mapping[str, str]) -> str | None:
    for name in ("CORE_SUPABASE_ANON_KEY", "SUPABASE_ANON_KEY", "KAIROS_STAGING_ANON_KEY"):
        value = (environ.get(name) or "").strip()
        if value:
            return value
    return None


def run_staging_e2e(
    *,
    http: HttpJson,
    environ: Mapping[str, str] | None = None,
    log: Callable[[str], None] = print,
    log_err: Callable[[str], None] | None = None,
) -> int:
    """Run Observer hops (if JWT) then vendor-secret / checkout phases."""
    env = os.environ if environ is None else environ
    err = log_err or (lambda msg: print(msg, file=sys.stderr))
    functions_base = (env.get("KAIROS_STAGING_FUNCTIONS_BASE") or DEFAULT_FUNCTIONS_BASE).rstrip(
        "/"
    )

    resolved = resolve_staging_jwt(http=http, environ=env)
    if resolved.attempted_grant and not resolved.token:
        err(
            "Password grant failed "
            f"HTTP {resolved.grant_http} — credentials not logged. "
            "Check KAIROS_STAGING_EMAIL/PASSWORD."
        )
        return 3
    jwt = resolved.token
    if jwt:
        log("kairos_staging_e2e: Observer hops (Settings + checkout, no vendor secrets required)")
        results = run_observer_hops(
            http=http,
            jwt=jwt,
            anon_key=_anon_from_env(env),
            functions_base=functions_base,
        )
        failed = False
        for row in results:
            code = row.code or "ok"
            log(f"  {row.label} http={row.http} code={code} ok={row.ok}")
            if not row.ok:
                failed = True
        if failed:
            err("Observer hops failed — Settings EF TIER_FORBIDDEN / read contract regression.")
            return 3
        evidence = collect_remaining_evidence(
            http=http,
            jwt=jwt,
            anon_key=_anon_from_env(env),
            functions_base=functions_base,
        )
        proven = proven_remaining_hops(evidence)
        log("kairos_staging_e2e: remaining hop product-state")
        for name in REMAINING_LIVE_HOPS:
            log(f"  {name} proven={proven[name]}")
        unproven = remaining_hops_unproven(proven)
        if not unproven:
            log("kairos_staging_e2e: all remaining hops proven from Settings reads")
            return 0
    else:
        log(
            "kairos_staging_e2e: Observer hops skipped "
            "(set KAIROS_STAGING_USER_JWT or KAIROS_STAGING_EMAIL+PASSWORD+ANON)"
        )
        proven = {}
        unproven = remaining_hops_unproven()

    log("kairos_staging_e2e: checking required secret *names* (values never printed)")
    log(f"  inventory_count={len(KAIROS_STAGING_REQUIRED_SECRETS)}")
    missing = missing_kairos_staging_secrets(env)
    if missing:
        err(format_missing_secrets_failure(missing))
        err(format_remaining_hops_failure(unproven))
        return 2

    if not jwt:
        err(format_missing_secrets_failure(["KAIROS_STAGING_USER_JWT"]))
        err(format_remaining_hops_failure(unproven))
        return 2

    status, body = http(
        "POST",
        f"{functions_base}/create-checkout-session",
        headers={"Authorization": f"Bearer {jwt}"},
        body={"tier": "baseline", "interval": "monthly"},
    )
    code = _response_code(body) or "ok"
    log(f"  checkout_http={status} code={code}")
    if status >= 500 and _response_code(body) in CHECKOUT_CONFIG_MISS_CODES:
        err(
            "Checkout still misconfigured on core EF — set the same secret names "
            f"via `supabase secrets set` (code={_response_code(body)})."
        )
        return 3
    if status not in {200, 201} or not body.get("url"):
        err(f"Unexpected checkout response HTTP {status} code={_response_code(body)}")
        return 3

    wh_status, wh_body = http(
        "POST",
        f"{functions_base}/stripe-webhook",
        body={"id": "evt_staging_probe"},
    )
    wh_code = _response_code(wh_body) or "ok"
    log(f"  webhook_http={wh_status} code={wh_code}")
    if _response_code(wh_body) == "STRIPE_NOT_CONFIGURED":
        err("stripe-webhook still STRIPE_NOT_CONFIGURED on core EF.")
        return 3

    err(format_remaining_hops_failure(unproven))
    log(
        "kairos_staging_e2e: checkout cleared config errors. "
        "Remaining hops still unproven — exit 4, not 0."
    )
    return EXIT_REMAINING_HOPS_UNPROVEN


__all__ = [
    "CHECKOUT_CONFIG_MISS_CODES",
    "DEFAULT_FUNCTIONS_BASE",
    "EXIT_REMAINING_HOPS_UNPROVEN",
    "OBSERVER_HOPS",
    "REMAINING_LIVE_HOPS",
    "HopExpectation",
    "HttpJson",
    "JwtResolution",
    "ObserverHop",
    "ProbeResult",
    "RemainingHopEvidence",
    "collect_remaining_evidence",
    "format_remaining_hops_failure",
    "hop_ok",
    "password_grant_access_token",
    "proven_remaining_hops",
    "remaining_hops_unproven",
    "resolve_staging_jwt",
    "run_observer_hops",
    "run_staging_e2e",
]
