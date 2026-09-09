"""Per-request LLM auth funnel for digigraph's FastAPI service.

Relocated from the former monolithic ``digigraph.llm`` (#632 P2). Parses the
per-request auth headers digichat/digikey forward and feeds digillm's
provider-agnostic override contextvars:

- ``X-LiteLLM-Proxy-Key`` → :func:`digillm.set_proxy_key` (the LiteLLM Bearer used
  on the default client path).
- ``X-BYOK-Key`` / ``X-BYOK-Provider`` / ``X-BYOK-Model`` → :func:`digillm.set_byok` for
  OpenAI, OpenRouter, Gemini, and Anthropic — the entries in :data:`_BYOK_BASE_URLS`.
  A key for any other provider is REFUSED with a 400 by ``byok_header_context`` in
  server.py: digigraph has no call path that would spend it, so accepting one meant
  answering on the operator's credentials while the user believed theirs was active
  (#1873). Non-OpenAI BYOK requires ``X-BYOK-Model`` so the spend path never falls
  through to the operator key with an ambiguous model id.

digigraph keeps its own ``(key, provider)`` BYOK contextvar so
:func:`get_byok_override` still reports the provider tag — digillm's ``get_byok``
only carries ``(api_key, base_url)``.

Header parsing lives here, not in digillm: digillm never imports FastAPI nor
accepts ``Request`` objects.
"""

from __future__ import annotations

import json
import logging
import os
from contextvars import ContextVar
from pathlib import Path
from typing import Any, NamedTuple  # score:allow untyped any — Starlette Request kept loose
from urllib.parse import urlsplit

from digillm import (
    clear_byok,
    is_registered_provider,
    reset_byok,
    reset_proxy_key,
    set_byok,
    set_proxy_key,
)
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator

logger = logging.getLogger(__name__)


# Single source of truth for the BYOK provider allowlist — see
# docs/superpowers/specs/2026-08-13-digichat-byok-model-catalog-design.md.
# Loaded ONCE at import time (not the mtime-recheck-per-call pattern
# model_config.py uses for model_modes.yaml — this changes at the pace of a
# code review, not a redeploy). A missing or malformed catalog raises here,
# crashing the process at startup — loud and immediate in deploy health
# checks, rather than a running process that silently 400s every BYOK
# request. See the design spec's Error handling section for why this
# deliberately differs from model_config.py's own reload behavior.
#
# Path resolution honors ``DIGI_CONFIG_PATH`` when set (the same env var
# model_config.py's loaders read — see its ``_load_model_modes``), so an
# operator who points the service at a config directory gets the catalog
# from there instead of a hardcoded, image-layout-dependent guess. Falling
# back to a bare ``Path(DIGI_CONFIG_PATH or "config")`` (model_config.py's
# own pattern) would NOT work here when the var is unset: that resolves
# relative to CWD, whereas this fallback must keep resolving to
# ``<repo>/config`` for local dev, editable installs, and tests regardless
# of the process's working directory — hence the ``__file__``-relative
# fallback is kept unchanged and only used when the env var is absent.
def _resolve_byok_catalog_path() -> Path:
    config_dir_override = os.environ.get("DIGI_CONFIG_PATH")
    if config_dir_override:
        return Path(config_dir_override) / "byok-providers.json"
    return Path(__file__).resolve().parents[3] / "config" / "byok-providers.json"


_BYOK_CATALOG_PATH = _resolve_byok_catalog_path()


class _ByokCatalogEntry(BaseModel):
    """Strict schema for one ``config/byok-providers.json`` entry.

    ``strict=True`` rejects type-coercion surprises a plain ``dict.get()`` walk
    would silently accept — a JSON string ``"false"`` for ``requiresModel``
    (Python's ``bool("false") is True``) or a JSON ``null`` for ``id``
    (``str(None).lower() == "none"``, which would collide with a real future
    provider literally named "none"). ``baseUrl`` is additionally restricted to
    absolute ``https://`` URLs: this value is where ``push_byok_header`` sends
    the user's own BYOK key (see module docstring), so an ``http://`` catalog
    entry would transmit that key in cleartext (CWE-319).
    """

    model_config = ConfigDict(strict=True)

    id: str
    baseUrl: str
    requiresModel: bool = False
    # Read for one purpose: the remediation example in byok_default_model_refusal.
    # Optional because an entry without examples still routes fine — the refusal
    # just drops its parenthetical. digichat does not read this field at runtime; it
    # hand-copies the same list into `byokModelPresets`, pinned to this catalog by
    # use-byok-key.catalog-parity.test.ts. So the model the refusal names is the same
    # one the UI offers — that parity test is load-bearing for this message.
    fallbackModels: list[str] = []

    @field_validator("id")
    @classmethod
    def _id_non_empty(cls, v: str) -> str:
        normalized = v.strip().lower()
        if not normalized:
            raise ValueError("id must be a non-empty string")
        return normalized

    @field_validator("fallbackModels", mode="before")
    @classmethod
    def _clean_examples(cls, v: object) -> list[str]:
        """Salvage what is usable and warn; never fail the load over a parenthetical.

        Two departures from every other field here, both deliberate.

        It **strips**, because this value reaches user-facing copy verbatim:
        ``"  gpt-4o  "`` rendered as ``(e.g.   gpt-4o  )``. It is not the only such
        field — ``server.py``'s ``byok_provider_unsupported`` joins the catalog ``id``
        values into its message — but that one is stripped already by ``_id_non_empty``, and
        this validator rejected blanks *without* stripping the survivors. That
        asymmetry is what let padding through.

        It does **not raise**, because a bad value here cannot break routing — an
        entry without examples still routes fine, the refusal just drops its
        parenthetical. Fail-loud exists so a broken catalog cannot silently 400 every
        BYOK request; that reasoning does not reach a cosmetic field. It matters
        concretely: this key was an *ignored extra* until it was typed, so an
        operator catalog under ``DIGI_CONFIG_PATH`` carrying ``fallbackModels: null``
        imported fine before and would otherwise now crash digigraph at startup over
        a parenthetical. Warn instead, so a typo still leaves a trace.
        """
        if not isinstance(v, list):
            logger.warning("BYOK catalog: fallbackModels is not a list, ignoring: %r", v)
            return []
        cleaned = [m.strip() for m in v if isinstance(m, str) and m.strip()]
        if len(cleaned) != len(v):
            logger.warning(
                "BYOK catalog: dropped %d unusable fallbackModels entry/entries",
                len(v) - len(cleaned),
            )
        return cleaned

    @field_validator("baseUrl")
    @classmethod
    def _https_only(cls, v: str) -> str:
        parsed = urlsplit(v)
        if parsed.scheme != "https" or not parsed.netloc:
            raise ValueError(f"baseUrl must be an absolute https:// URL, got: {v!r}")
        return v


def _load_byok_catalog(path: Path) -> tuple[dict[str, str], frozenset[str], dict[str, str]]:
    if not path.exists():
        raise FileNotFoundError(f"BYOK provider catalog not found at {path}")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        raise ValueError(f"BYOK provider catalog at {path} is not valid JSON: {e}") from e
    if not isinstance(raw, list) or not raw:
        raise ValueError(f"BYOK provider catalog at {path} must be a non-empty JSON array")
    base_urls: dict[str, str] = {}
    model_required: set[str] = set()
    examples: dict[str, str] = {}
    seen_ids: set[str] = set()
    for entry in raw:
        try:
            parsed_entry = _ByokCatalogEntry.model_validate(entry)
        except ValidationError as e:
            raise ValueError(f"BYOK provider catalog entry invalid: {entry!r}: {e}") from e
        if parsed_entry.id in seen_ids:
            raise ValueError(f"BYOK provider catalog has duplicate id: {parsed_entry.id!r}")
        seen_ids.add(parsed_entry.id)
        base_urls[parsed_entry.id] = parsed_entry.baseUrl
        if parsed_entry.requiresModel:
            model_required.add(parsed_entry.id)
        if parsed_entry.fallbackModels:
            examples[parsed_entry.id] = parsed_entry.fallbackModels[0]
    return base_urls, frozenset(model_required), examples


# The one table: a provider here is routed to its own endpoint with the user's key.
_BYOK_BASE_URLS, BYOK_MODEL_REQUIRED_PROVIDERS, _BYOK_MODEL_EXAMPLES = _load_byok_catalog(
    _BYOK_CATALOG_PATH
)
BYOK_ROUTABLE_PROVIDERS = tuple(_BYOK_BASE_URLS)


def byok_provider_supported(provider: str) -> bool:
    """True when a BYOK key for *provider* is actually spent on that provider."""
    return provider.strip().lower() in _BYOK_BASE_URLS


def byok_model_required(provider: str) -> bool:
    """True when *provider* must send ``X-BYOK-Model`` to spend the user key."""
    return provider.strip().lower() in BYOK_MODEL_REQUIRED_PROVIDERS


def byok_routable_model(provider: str, model: str) -> str:
    """Return *model* in the form that actually spends a BYOK key for *provider*.

    A provider in digillm's registry carries its own prefix in its canonical model
    string (``gemini/…``, ``openrouter/…``), so the prefix is stripped and re-applied.
    That is idempotent, and it preserves OpenRouter's legitimate vendor sub-slugs:
    ``anthropic/claude-sonnet-4`` becomes ``openrouter/anthropic/claude-sonnet-4``,
    not a request billed to the operator's Anthropic key.

    ``openai`` is deliberately *not* in that registry — its canonical model string is
    bare (``gpt-4o-mini``) — so nothing is prefixed onto it. That asymmetry is the
    whole reason :func:`byok_model_routes_elsewhere` exists.

    The provider's own prefix is stripped to a **fixpoint**, not once, and that loop
    is load-bearing rather than tidiness. :func:`byok_model_routes_elsewhere` is
    asked the same question at two doors that hold two different strings — the
    middleware holds the raw header, the resolver holds the once-stripped slug from
    ``_normalize_byok_model_slug`` — so the verdict must not depend on how many of
    the provider's own prefixes have already been removed. Stripping to a fixpoint
    is exactly that invariance. Weaken it to a single strip and the doors diverge at
    depth two: ``X-BYOK-Provider: openai`` with ``openai/openai/gemini/…`` leaves the
    middleware's copy reading ``openai/gemini/…``, whose head ``openai`` is *not* a
    registered provider, so it passes — and is then dropped at the resolver, which
    sees one prefix fewer. Same header, two answers.
    """
    prov = provider.strip().lower()
    slug = model.strip()
    prefix = f"{prov}/"
    while slug.startswith(prefix):
        slug = slug[len(prefix) :]
    return f"{prov}/{slug}" if is_registered_provider(prov) else slug


def _routes_to_another_provider(provider: str, model: str) -> bool:
    """True when *model*, sent exactly as given, is served by a provider other than *provider*.

    The single billing rule behind both public predicates below: a model leading with
    a *registered* provider prefix is routed to that provider's env-keyed client, so
    if that prefix is not the declared BYOK provider the operator pays. A bare model,
    or one whose head is not in digillm's registry (``ollama/…``, ``openai``'s bare
    slugs), carries no such prefix and is served by whatever client the BYOK override
    already installed — the user's.

    The two callers differ only in *which string* they hand in; see each for why.
    """
    head, sep, _rest = model.partition("/")
    if not sep or not is_registered_provider(head):
        return False
    return head != provider.strip().lower()


def byok_model_routes_elsewhere(provider: str, model: str) -> bool:
    """True when *model* under BYOK *provider* would be billed to an operator key.

    ``X-BYOK-Model`` is caller-supplied and untrusted. ``X-BYOK-Provider: openai``
    with ``X-BYOK-Model: gemini/gemini-2.5-flash`` survives every other check: the
    provider is routable, a model is present, and openai adds no prefix of its own —
    so the gemini prefix reaches digillm intact, which builds the gemini client on the
    operator's ``GEMINI_API_KEY``. The user's key is accepted, displayed as active,
    never spent, and someone else pays.

    The test is on the *routable* form rather than on the raw header, which is why it
    is one rule for all providers instead of an openai special case: a registered
    provider's model is re-prefixed to itself and can never conflict, so only a
    provider that adds no prefix can carry a foreign one through. Prefixes are read
    from digillm's registry — the same source ``_parse_provider_prefix`` in
    model_config uses — because that registry, not the BYOK catalog, is what decides
    which env-keyed client gets built.
    """
    return _routes_to_another_provider(provider, byok_routable_model(provider, model))


def byok_operator_model_routes_elsewhere(provider: str, model: str) -> bool:
    """True when the *operator-resolved* *model* would be billed to an operator key.

    Same billing rule as :func:`byok_model_routes_elsewhere`, asked about a model the
    caller never sent but the operator's own configuration produced — the tier default
    on the mode path, a ``phase_models`` override or an ``digiquant_models.yaml``
    capability model on the phase path. Whichever one it is reaches digillm
    **verbatim**. That difference is the whole reason this is a second entry point
    rather than a reuse, and it is not a latent distinction — it changes the answer.

    Both callers pass such a string: ``server.py`` passes ``operator_default_model()``
    (the tier default, the only one it can see), and ``_apply_byok_model_override``
    passes its own *resolved* — which on the phase path is the override or capability
    model the middleware never saw.

    ``byok_model_routes_elsewhere`` first normalizes through
    :func:`byok_routable_model`, which is correct for an ``X-BYOK-Model`` header
    because ``_apply_byok_model_override`` really does route the normalized form. But
    for a *registered* provider that normalization re-prefixes to the provider
    itself, so the head always equals the declared provider and the verdict is
    unconditionally ``False``. Ask it about ``provider="openrouter"`` with an
    operator default of ``gemini/gemini-2.5-flash`` and it answers "fine" — while
    digillm builds a Gemini client on the operator's ``GEMINI_API_KEY``. Over HTTP
    that shape cannot arrive (every registered provider is ``requiresModel: true``,
    so the middleware refuses first), but ``_apply_byok_model_override`` exists
    precisely to hold for in-process callers that never passed the middleware, and
    there it would be wrong today rather than eventually.

    So the operator's model is tested as-sent, with no normalization at all.
    """
    return _routes_to_another_provider(provider, model)


BYOK_DEFAULT_MODEL_MISMATCH_CODE = "byok_default_model_provider_mismatch"


def byok_default_model_refusal(provider: str) -> str:
    """Refusal text for a bound BYOK key the deployment's own default would not spend.

    Distinct from ``byok_model_required`` on purpose, with the same remediation
    sentence. ``byok_model_required`` is a property of the *provider* — digichat's
    own catalog knows it and never lets such a request leave the browser — so
    answering it here for a provider whose catalog entry says ``requiresModel:
    false`` would tell the operator their frontend is broken when it is not. This
    code says something the frontend cannot know: *this deployment's* default is
    served by someone else.

    Names neither the *operator's* model slug nor the key. That slug is the
    operator's configuration, not the caller's input, and disclosing it to an
    anonymous caller buys no remediation — the fix is the same either way. The
    example it does name is the provider's own first ``fallbackModels`` entry from
    the public catalog, so it discloses nothing and is always a slug that provider
    declares. A hardcoded example cannot be: the previous ``gpt-4o-mini`` was told
    to four of the five providers that do not serve it — anthropic, gemini, xai,
    and openrouter, whose own slug is the prefixed ``openai/gpt-4o-mini``.

    Phrased as "a model served by <provider>" rather than "a <provider> model" so
    no indefinite article has to agree with a provider id. The old construction ran
    for all five and read wrong for four of them (``a openai``, ``a anthropic``,
    ``a xai``, ``a openrouter``; only ``a gemini`` scans).
    """
    normalized = provider.strip().lower()
    example = _BYOK_MODEL_EXAMPLES.get(normalized)
    hint = f" (e.g. {example})" if example else ""
    return (
        f"This deployment's default model is served by a provider other than {provider!r}, "
        f"so your {provider} key would not be the one billed. Send X-BYOK-Model with a model "
        f"served by {provider}{hint} to spend your own key."
    )


# digigraph's own per-request BYOK record: (api_key, provider) where provider is
# "openai" | "anthropic" | "openrouter" | "gemini". Distinct from digillm's
# (api_key, base_url) override so get_byok_override() can still report the provider.
# Never logged or persisted.
_byok_override: ContextVar[tuple[str, str] | None] = ContextVar("dg_byok_override", default=None)
# BYOK model slug from X-BYOK-Model (e.g. openai/gpt-4o-mini, gemini/…). Never logged.
_byok_model_override: ContextVar[str | None] = ContextVar("dg_byok_model_override", default=None)


def push_lite_llm_proxy_header(request: Any) -> object:
    """Parse ``X-LiteLLM-Proxy-Key`` → digillm proxy-key override; return a token for pop.

    Pass the returned token to :func:`pop_lite_llm_proxy` (typically in a
    ``finally`` block) to restore the previous value.
    """
    raw = request.headers.get("x-litellm-proxy-key")
    val = raw.strip() if raw else None
    return set_proxy_key(val)


def pop_lite_llm_proxy(token: object) -> None:
    """Restore the digillm proxy-key override saved by :func:`push_lite_llm_proxy_header`."""
    reset_proxy_key(token)


class _ByokToken(NamedTuple):
    """Reset tokens for the digigraph + digillm BYOK overrides (opaque to callers)."""

    dg: object
    model: object
    llm: object | None


def _normalize_byok_model_slug(raw: str, provider: str) -> str:
    """Drop one redundant ``provider/`` prefix from a caller-supplied model slug.

    One strip, deliberately — not a fixpoint. The guard that decides whether this
    slug may be routed reads it through :func:`byok_routable_model`, which strips the
    provider's own prefix to a fixpoint, so how many prefixes *this* function leaves
    behind cannot change any verdict or any routed model. A second strip here would
    only alter what ``get_byok_model_override`` reports.

    (The former ``provider == "openrouter"`` special case was unreachable: when the
    provider *is* ``openrouter``, ``prefix`` already equals ``"openrouter/"`` and the
    branch above consumed it; when it is not, the conjunct is false.)
    """
    trimmed = raw.strip()
    prefix = f"{provider}/"
    if trimmed.startswith(prefix):
        return trimmed[len(prefix) :]
    return trimmed


def push_byok_header(request: Any) -> _ByokToken:
    """Parse ``X-BYOK-Key`` / ``X-BYOK-Provider`` / ``X-BYOK-Model`` and bind BYOK overrides.

    Sets digigraph's ``(key, provider)`` contextvar (for :func:`get_byok_override`)
    and, for routable providers, feeds digillm's BYOK override so the LLM
    client talks directly to the provider with the user key. Reaching this function
    with an unroutable provider no longer happens over HTTP: ``byok_header_context``
    in server.py refuses those with a 400 first (#1873).

    Returns an opaque token for :func:`pop_byok` (use in a ``finally`` block).
    """
    key = (request.headers.get("x-byok-key") or "").strip()
    provider = (request.headers.get("x-byok-provider") or "openai").strip().lower()
    model_raw = (request.headers.get("x-byok-model") or "").strip()
    model_slug = _normalize_byok_model_slug(model_raw, provider) if model_raw else ""
    val = (key, provider) if key else None
    dg_token = _byok_override.set(val)
    model_token = _byok_model_override.set(model_slug or None)
    llm_token: object | None = None
    if val is not None:
        base_url = _BYOK_BASE_URLS.get(provider)
        if base_url is not None:
            llm_token = set_byok(key, base_url)
    return _ByokToken(dg=dg_token, model=model_token, llm=llm_token)


def pop_byok(token: _ByokToken) -> None:
    """Restore both BYOK overrides saved by :func:`push_byok_header`."""
    if token.llm is not None:
        reset_byok(token.llm)
    _byok_model_override.reset(token.model)
    _byok_override.reset(token.dg)


def clear_byok_bindings() -> None:
    """Drop every BYOK binding in the *current* context, token-free.

    For code that inherited the bindings through :func:`contextvars.copy_context`
    rather than binding them itself: a copy carries the values but none of the reset
    tokens, so :func:`pop_byok` cannot be used. The streaming worker in ``server.py``
    calls this from its own ``finally`` -- its copy is taken while the request is
    still open, and outlives the request's ``pop_byok``, so without this the user's
    key stays resident in the worker's context until the thread ends. Clearing the
    copy cannot disturb the request that spawned it; a copy is a snapshot, not a view.

    Do not call this in the frame that ran :func:`push_byok_header`: it would blank
    the values while stranding that frame's tokens. Use :func:`pop_byok` there.
    """
    clear_byok()
    _byok_model_override.set(None)
    _byok_override.set(None)


def get_byok_override() -> tuple[str, str] | None:
    """Return the active per-request BYOK ``(api_key, provider)`` override, or ``None``."""
    return _byok_override.get()


def get_byok_model_override() -> str | None:
    """Return the active BYOK model slug from ``X-BYOK-Model``, or ``None``."""
    return _byok_model_override.get()
