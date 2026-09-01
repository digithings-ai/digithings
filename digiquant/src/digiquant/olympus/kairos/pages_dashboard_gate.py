"""Fail-closed gate: do not redeploy /dashboard Edge Functions until Pages is 200.

Staging E2E pins ``GET /settings/app-urls`` to ``https://digiquant.io/dashboard/...``.
Live Pages still serve ``/olympus`` until [#3356](https://github.com/digithings-ai/digithings/pull/3356)
merges. Redeploying settings / checkout / portal with ``/dashboard`` URLs while
that path 404s would break Auth callbacks and billing returns.

Default is ``--check`` (probe only). ``--apply`` deploys the three APP_URL
functions only after every required path returns 200 on the public origin
**and** this checkout pins ``/dashboard`` URLs and mounts
``POST /access/redeem-invite`` (migration 112 tables are already on ``core``)
**and** the live settings ESZIP still contains those executable markers after
deploy (settings v32 has neither). Never weakens ``public_app_urls_ok``.
"""

from __future__ import annotations

import argparse
import http.client
import os
import re
import subprocess
import urllib.error
import urllib.request
from collections.abc import Callable, Sequence
from pathlib import Path
from urllib.parse import urlparse

from pydantic import BaseModel, ConfigDict, Field

from digiquant.olympus.kairos.staging_e2e import DEFAULT_PUBLIC_APP_ORIGIN
from digiquant.olympus.kairos.vendor_secret_files import (
    CORE_PROJECT_REF,
    function_deploy_argv,
)

EXIT_PAGES_DASHBOARD_NOT_READY: int = 3
EXIT_APPLY_FAILED: int = 4
EXIT_CHECKOUT_STALE: int = 5
EXIT_LIVE_EF_STALE: int = 6
MANAGEMENT_API_ORIGIN = "https://api.supabase.com"
MANAGEMENT_API_USER_AGENT = "Mozilla/5.0 kairos-pages-dashboard-gate/1.0 (+digithings)"

_REPO_ROOT = Path(__file__).resolve().parents[5]
_SETTINGS_HANDLERS = (
    Path("digiquant") / "supabase" / "functions" / "_shared" / "settings-handlers.ts"
)
_APP_URL_TS = Path("digiquant") / "supabase" / "functions" / "_shared" / "app-url.ts"
_REDEEM_INVITE_RE = re.compile(r'method\s*===\s*"POST"\s*&&\s*path\s*===\s*"/access/redeem-invite"')
_ALPACA_DASHBOARD_RE = re.compile(
    r'export\s+const\s+ALPACA_OAUTH_CALLBACK_PATH\s*=\s*"/dashboard/settings/brokers/callback/"\s*;'
)
_SETTINGS_DASHBOARD_RE = re.compile(
    r'export\s+const\s+SETTINGS_PATH\s*=\s*"/dashboard/settings/"\s*;'
)
_ALPACA_OLYMPUS_RE = re.compile(r'export\s+const\s+ALPACA_OAUTH_CALLBACK_PATH\s*=\s*"/olympus/')
_SETTINGS_OLYMPUS_RE = re.compile(r'export\s+const\s+SETTINGS_PATH\s*=\s*"/olympus/')

DASHBOARD_PATHS: tuple[str, ...] = (
    "/dashboard/",
    "/dashboard/login/",
    "/dashboard/auth/callback/",
    "/dashboard/settings/",
)

# Functions that inline APP_URL + /dashboard paths. Do not include
# stripe-webhook — that deploy is --no-verify-jwt and is not the path cutover.
DASHBOARD_URL_FUNCTIONS: tuple[str, ...] = (
    "create-checkout-session",
    "customer-portal",
    "settings",
)

PROBE_USER_AGENT = "kairos-pages-dashboard-gate/1.0 (+digithings)"
_PROBE_HEADERS = {
    # Cloudflare 403s the default Python-urllib UA; curl from this VM gets
    # the real origin status (/olympus 200, /dashboard 404 as of 2026-09-01).
    "User-Agent": PROBE_USER_AGENT,
}

ProbeFn = Callable[[str], tuple[int, str]]
RunArgv = Callable[[Sequence[str]], None]
LiveSourceFn = Callable[[], str]
HttpBytesFn = Callable[[str], bytes]


class LiveSettingsFetchError(Exception):
    """Live settings ESZIP could not be fetched. Never includes token values."""


class PagesPathResult(BaseModel):
    """One public-path probe — status + final URL, no bodies."""

    model_config = ConfigDict(frozen=True)

    path: str
    http: int
    final_url: str


class PagesDashboardReport(BaseModel):
    """Sanitized probe report for the Pages half of the path cutover."""

    model_config = ConfigDict(frozen=True)

    origin: str
    results: tuple[PagesPathResult, ...] = Field(default_factory=tuple)

    @property
    def ready(self) -> bool:
        return all(_path_ready(item, self.origin) for item in self.results)


def _path_is_dashboard(final_url: str, origin: str) -> bool:
    parsed = urlparse(final_url)
    origin_parsed = urlparse(origin)
    if parsed.scheme != origin_parsed.scheme:
        return False
    if parsed.netloc.lower() != origin_parsed.netloc.lower():
        return False
    path = parsed.path or "/"
    lowered = path.lower()
    if "/olympus" in lowered:
        return False
    return path == "/dashboard" or path.startswith("/dashboard/")


def _path_ready(item: PagesPathResult, origin: str | None = None) -> bool:
    expected_origin = origin or DEFAULT_PUBLIC_APP_ORIGIN
    return item.http == 200 and _path_is_dashboard(item.final_url, expected_origin)


def probe_url(url: str, *, timeout: float = 15.0) -> tuple[int, str]:
    """GET a URL; return (status, final_url). Does not return bodies."""
    request = urllib.request.Request(url, method="GET", headers=_PROBE_HEADERS)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return int(response.status), str(response.geturl())
    except urllib.error.HTTPError as exc:
        final = str(getattr(exc, "url", None) or url)
        return int(exc.code), final
    except OSError:
        return 0, url


def probe_pages_dashboard(
    *,
    origin: str = DEFAULT_PUBLIC_APP_ORIGIN,
    probe: ProbeFn = probe_url,
) -> PagesDashboardReport:
    results: list[PagesPathResult] = []
    base = origin.rstrip("/")
    for path in DASHBOARD_PATHS:
        http, final_url = probe(f"{base}{path}")
        results.append(PagesPathResult(path=path, http=http, final_url=final_url))
    return PagesDashboardReport(origin=base, results=tuple(results))


def _strip_ts_comments(source: str) -> str:
    without_block = re.sub(r"/\*.*?\*/", "", source, flags=re.DOTALL)
    stripped: list[str] = []
    for line in without_block.splitlines():
        if "//" in line:
            line = line[: line.index("//")]
        stripped.append(line)
    return "\n".join(stripped)


def _regex_in_code(source: str, pattern: re.Pattern[str]) -> bool:
    """True when ``pattern`` matches a non-comment occurrence."""
    text = _strip_ts_comments(source)
    return pattern.search(text) is not None


def settings_bundle_ready(source: str, *, live: bool = False) -> tuple[bool, str]:
    """Executable redeem-invite + ``/dashboard`` pins; ``/olympus`` pins fail."""
    where = "live settings bundle" if live else "checkout"
    extra = (
        " — deploy did not mount 112 redeem"
        if live
        else " — do not deploy settings from this tree (112 tables would sit unused)"
    )
    if not _regex_in_code(source, _REDEEM_INVITE_RE):
        return False, f"pages dashboard gate: {where} missing POST /access/redeem-invite{extra}"
    if not _regex_in_code(source, _ALPACA_DASHBOARD_RE):
        return (
            False,
            f"pages dashboard gate: {where} does not pin /dashboard Alpaca callback",
        )
    if not _regex_in_code(source, _SETTINGS_DASHBOARD_RE):
        return (
            False,
            f"pages dashboard gate: {where} does not pin /dashboard settings path",
        )
    if _regex_in_code(source, _ALPACA_OLYMPUS_RE):
        return False, f"pages dashboard gate: {where} still pins /olympus Alpaca callback"
    if _regex_in_code(source, _SETTINGS_OLYMPUS_RE):
        return False, f"pages dashboard gate: {where} still pins /olympus settings path"
    return True, ""


def checkout_ready_for_ef_apply(repo_root: Path) -> tuple[bool, str]:
    """True when this tree can deploy settings after /dashboard is live.

    112 invite tables are on ``core``. Live settings v32 has no redeem-invite
    route. ``--apply`` must not deploy a checkout that still pins ``/olympus``
    or omits ``POST /access/redeem-invite``. Comment-only mentions do not count.
    """
    handlers = repo_root / _SETTINGS_HANDLERS
    app_url = repo_root / _APP_URL_TS
    try:
        source = handlers.read_text(encoding="utf-8") + "\n" + app_url.read_text(encoding="utf-8")
    except OSError:
        return False, "pages dashboard gate: settings EF source unreadable"
    return settings_bundle_ready(source, live=False)


def format_pages_dashboard_blocked(report: PagesDashboardReport) -> str:
    bits: list[str] = ["pages /dashboard not ready — do not redeploy settings EF"]
    for item in report.results:
        if _path_ready(item, report.origin):
            continue
        bits.append(f"{item.path} http={item.http}")
    return "; ".join(bits)


def _run_argv(argv: Sequence[str]) -> None:
    subprocess.run(argv, check=True, capture_output=True, text=True)


def _http_bytes(url: str, *, token: str, timeout: float = 60.0) -> bytes:
    request = urllib.request.Request(
        url,
        method="GET",
        headers={
            "Authorization": f"Bearer {token}",
            "Accept": "*/*",
            "User-Agent": MANAGEMENT_API_USER_AGENT,
        },
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return bytes(response.read())
    except urllib.error.HTTPError as exc:
        raise LiveSettingsFetchError(f"live settings bundle HTTP {int(exc.code)}") from None
    except (OSError, http.client.HTTPException):
        raise LiveSettingsFetchError("live settings bundle fetch failed") from None


def fetch_live_settings_bundle(
    *,
    project_ref: str = CORE_PROJECT_REF,
    token: str | None = None,
    http_bytes: HttpBytesFn | None = None,
) -> str:
    """Download the live settings ESZIP. Never logs the token or bundle."""
    secret = (token if token is not None else os.environ.get("SUPABASE_ACCESS_TOKEN", "")).strip()
    if not secret:
        raise LiveSettingsFetchError("SUPABASE_ACCESS_TOKEN missing")
    url = f"{MANAGEMENT_API_ORIGIN}/v1/projects/{project_ref}/functions/settings/body"
    getter: HttpBytesFn = http_bytes or (lambda u: _http_bytes(u, token=secret))
    raw = getter(url)
    if not raw:
        raise LiveSettingsFetchError("live settings bundle empty")
    return raw.decode("latin-1")


def _verify_live_settings(
    log: Callable[[str], None],
    live_source: LiveSourceFn | None,
    *,
    project_ref: str,
) -> int:
    if live_source is None and os.environ.get("PYTEST_CURRENT_TEST"):
        log("pages dashboard gate: live_source required under pytest")
        return EXIT_LIVE_EF_STALE
    try:
        bundle = (
            live_source()
            if live_source is not None
            else fetch_live_settings_bundle(project_ref=project_ref)
        )
    except LiveSettingsFetchError as exc:
        log(f"pages dashboard gate: live settings fetch failed ({exc})")
        return EXIT_LIVE_EF_STALE
    ready, reason = settings_bundle_ready(bundle, live=True)
    if not ready:
        log(reason)
        return EXIT_LIVE_EF_STALE
    log("pages dashboard gate: live settings bundle has redeem-invite + /dashboard pins")
    return 0


def run_pages_dashboard_gate(
    *,
    apply: bool,
    log: Callable[[str], None],
    origin: str = DEFAULT_PUBLIC_APP_ORIGIN,
    probe: ProbeFn = probe_url,
    run: RunArgv = _run_argv,
    project_ref: str = CORE_PROJECT_REF,
    repo_root: Path | None = None,
    live_source: LiveSourceFn | None = None,
) -> int:
    report = probe_pages_dashboard(origin=origin, probe=probe)
    for item in report.results:
        log(f"pages probe {item.path} http={item.http}")
    if not report.ready:
        log(format_pages_dashboard_blocked(report))
        return EXIT_PAGES_DASHBOARD_NOT_READY
    if not apply:
        log("pages /dashboard ready — check only (pass --apply to deploy EF)")
        return 0
    ready, reason = checkout_ready_for_ef_apply(repo_root or _REPO_ROOT)
    if not ready:
        log(reason)
        return EXIT_CHECKOUT_STALE
    try:
        for function in DASHBOARD_URL_FUNCTIONS:
            log(f"pages dashboard gate: deploy {function}")
            run(function_deploy_argv(function, project_ref=project_ref))
    except (OSError, subprocess.CalledProcessError):
        log("pages dashboard gate apply failed (supabase output not echoed)")
        return EXIT_APPLY_FAILED
    log("pages dashboard gate: settings/checkout/portal deployed")
    return _verify_live_settings(log, live_source, project_ref=project_ref)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Deploy settings/checkout/portal only if live /dashboard paths are 200, "
        "this checkout has redeem-invite + /dashboard app URLs, and the live "
        "settings ESZIP contains those same executable markers",
    )
    parser.add_argument(
        "--origin",
        default=DEFAULT_PUBLIC_APP_ORIGIN,
        help="Public origin to probe (default: https://digiquant.io)",
    )
    args = parser.parse_args(argv)
    return run_pages_dashboard_gate(
        apply=args.apply,
        origin=args.origin,
        log=lambda msg: print(msg, flush=True),
    )


if __name__ == "__main__":
    raise SystemExit(main())
