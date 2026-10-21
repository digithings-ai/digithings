#!/usr/bin/env python3
"""Compose the digichat tenant registry from the host secret store.

DIG-4488. The digichat Worker reads its tenant registry from the secret
``DIGICHAT_EMBED_TENANTS``. That registry carries a per-tenant ``token``
and the operator MCP rows. The OCC token is a client secret, so the
registry can never live in the repository.

The repository may only carry an OVERLAY: the non-secret tenant fields
(slug, corpus routing, presentation). The overlay is merged onto the live
registry read from the host secret store. The live registry is always the
base, so an overlay can never remove a tenant and can never change a
token.

This script refuses, loudly, the failure that caused DIG-4488:
applying a repository file as the registry.

Two copies of the registry exist, and the Worker merges them host by host
(apps/digichat-cloudflare/src/tenants-kv.ts): the legacy Worker secret
``DIGICHAT_EMBED_TENANTS`` and the Workers KV key ``embed-tenants``. A KV
copy whose credential references resolve replaces the legacy copy for that
host, so the KV copy decides what a tenant sees. This tool composes and
applies both copies.

Usage
-----

Plan only (offline, prints no secret value):

    python3 scripts/digichat_tenant_registry.py compose \
        --live-from ~/.config/digithings/secrets/digichat-embed-tenants.deploy.json \
        --overlay infra/digichat-release/DIG-3556-staged-prod-tenant-config.json

Plan the KV copy as well (read from a file, so the plan stays offline):

    python3 scripts/digichat_tenant_registry.py compose \
        --live-from <host-store-file> \
        --kv-from ~/.config/digithings/secrets/embed-tenants.kv.json \
        --overlay <overlay-file>

Write both copies and recycle the container:

    python3 scripts/digichat_tenant_registry.py apply \
        --live-from <host-store-file> \
        --overlay infra/digichat-release/DIG-3556-staged-prod-tenant-config.json

The apply path needs Cloudflare credentials for ``wrangler kv key put``
and ``wrangler secret put`` and the digichat admin key for the container
reset. It reads the live KV copy itself, prints a plan and asks for a
typed confirmation before it writes anything. The container reads its
registry at boot, so the recycle is part of the same change as the
registry write: the two are one change, never two.

An apply always reads the live KV copy, because the write replaces the
whole document: a copy read earlier would drop every tenant another
operator added since. ``--kv-from`` in an apply is therefore a staleness
check, and the apply refuses when the copy does not name the same tenants
as the live one.

The KV copy holds credential references by name. Every tenant it carries
must name one, and the copy must not drop a field the legacy copy
carries: the Worker replaces the legacy entry for a tenant whose
references resolve, so a dropped field stops being served.

The OCC tenant carries no ``models`` section: its model picker stays
closed (DIG-4486 refused the picker, DIG-4750 confirmed the refusal).
Removing a ``models`` section from the OCC entry is a defect fix this
tool makes; adding one is a fresh ruling for Counsel, so every copy
refuses it.
"""

import argparse
import copy
import hashlib
import json
import os
import re
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Policy
# ---------------------------------------------------------------------------

# Keys of EmbedTenantConfig (apps/digichat/src/lib/embed-tenants.ts) that an
# overlay may set. Anything else is refused: an unknown key is either a
# shape mistake (a key the runtime does not read) or a place to smuggle a
# value past review.
ALLOWED_OVERLAY_KEYS = frozenset(
    [
        "slug",
        "aliases",
        "backend",
        "gateMode",
        "theme",
        "defaultLanguage",
        "skin",
        "accent",
        "attribution",
        "title",
        "welcome",
        "welcomeBody",
        "suggestions",
        "placeholder",
        "lockedContact",
        "activityDetail",
        "showByok",
        "showLanguageSelector",
        "showStatusBar",
        "webSearch",
        "view",
        "thinking",
        "layout",
        "attachments",
        "dictation",
        "speech",
        "sources",
        "branchPicker",
        "pageContext",
        "tools",
        "models",
        "llmAccess",
        "gate",
        "requiredPlanTier",
    ]
)

# Never taken from an overlay. `token` is the per-tenant secret; `mcp`
# rows carry the operator MCP server credentials.
FORBIDDEN_OVERLAY_KEYS = frozenset(["token", "mcp"])

# Keys of the nested objects an overlay may set. A key the runtime does not
# read is refused: it is either a shape mistake (a key at the wrong level)
# or a place to smuggle a value past review. The staged DIG-3556 file
# carried `gate.webSearch`; the runtime reads `webSearch` at the top level
# and `gate.consumeUrl` only, so that key would have been dead weight.
ALLOWED_NESTED_KEYS = {
    "backend": frozenset(
        [
            "type",
            "digisearchIndex",
            "vaultPathPrefix",
            "projectEndpoint",
            "agentName",
            "baseUrl",
            "model",
            "apiKeyEnv",
        ]
    ),
    "gate": frozenset(["consumeUrl"]),
    "accent": frozenset(["color", "foreground"]),
    "models": frozenset(
        [
            "default",
            "available",
            "allowPicker",
            "catalog",
            "priceCapUsdPerMillion",
            "premiumCapUsdPerMillion",
            "costPerWindow",
            "presets",
            "showFullList",
            "minContextTokens",
        ]
    ),
    "models.costPerWindow": frozenset(["usd", "windowSeconds"]),
    "tools": frozenset(["allowUserToggle", "catalog"]),
    "tools.catalog": frozenset(["id", "default", "label", "tools"]),
}

# Keys allowed for the objects inside a list.
ALLOWED_LIST_ITEM_KEYS = {
    "tools.catalog": frozenset(["id", "default", "label", "tools"]),
    "tools.catalog.tools": frozenset(["id", "label"]),
}

# Paths where the runtime reads an OBJECT. A scalar there is a shape
# mistake, not a value to set, so it is refused by name instead of
# failing deep inside the merge.
OBJECT_OVERLAY_PATHS = frozenset(
    path for path in ALLOWED_NESTED_KEYS if path not in ALLOWED_LIST_ITEM_KEYS
)

# The OCC tenant is a client tenant. Its corpus routing and vault path are
# set by the rollout script (scripts/occ_invite_key_write.sh, DIG-4043) and
# live in the host secret store, so a repository overlay may neither carry
# nor change them. The corpus name itself stays in the private release-lane
# paths: this public script states the rule without writing it down.
OCC_HOST = "occ.digithings.ai"
# Backend keys the overlay may not set for the OCC tenant.
OCC_LOCKED_BACKEND_KEYS = ("digisearchIndex", "vaultPathPrefix")
# The retired OCC ticket corpus must never be routed to
# (scripts/occ_invite_key_write.sh enforces the same rule).
FORBIDDEN_INDEX = "occ_tickets"

# DIG-4486 refused an OCC model picker and DIG-4750 confirmed that refusal:
# a raw `models.available` id list does not belong on a client tenant.
# digichat 2.6.6 narrows that, at the product owner's request: a catalog
# policy (cap, presets, whether the full list is shown) is allowed. A raw
# `available` array is still refused on the way in and stripped from a live
# copy. This is not a Counsel ruling that the open list is fine.
OCC_MODELS_KEY = "models"

# The Workers KV copy of the registry. A KV copy whose credential references
# resolve replaces the legacy Worker secret for that host
# (apps/digichat-cloudflare/src/tenants-kv.ts), so the KV copy is the one
# that decides what a tenant sees. The KV copy holds references by name,
# never values.
KV_KEY = "embed-tenants"
KV_BINDING = "DIGICHAT_TENANTS_KV"
KV_CONFIG_FILE = "wrangler.toml"
DEFAULT_WORKER_DIR = "apps/digichat-cloudflare"
DEFAULT_WRANGLER_CMD = "npx --yes wrangler@4.133.0"

# A credential reference the Worker can resolve. The runtime resolves only
# names of this shape (apps/digichat-cloudflare/src/tenants-kv.ts), so a name
# of another shape is an unresolved reference, and an unresolved reference
# keeps the legacy copy: the KV write would have no effect at all.
CREDENTIAL_REF_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]*$")

# Fields the KV copy may leave out while the legacy copy carries them. The
# KV copy replaces the legacy entry for a host, so a field that lives only
# in the legacy copy stops being served when the KV copy is written.
# `token` is the credential value: it must not live in the KV copy.
# `models` is removed on purpose for the OCC tenant.
KV_DROP_ALLOWED = frozenset(["token", OCC_MODELS_KEY])

# The directory this script lives in. The containment guard resolves the
# repository that OWNS this tool from here, never from the caller's
# working directory.
SCRIPT_DIR = os.path.dirname(os.path.realpath(__file__))

SECRET_NAME = "DIGICHAT_EMBED_TENANTS"
DEFAULT_WORKER = "digithings-digichat"
DEFAULT_ADMIN_KEY_FILE = os.path.expanduser("~/.config/digithings/secrets/digichat-admin-key.txt")
DEFAULT_LIVE_FILE = os.path.expanduser(
    "~/.config/digithings/secrets/digichat-embed-tenants.deploy.json"
)
RESET_URL = "https://digithings.ai/_digichat-admin/container/reset"
APPLY_CONFIRM_WORD = "APPLY"


class RegistryRefusal(Exception):
    """A guard refused the change. The message is the finding."""


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def fingerprint(obj):
    """sha256 prefix of a JSON object. Never a value."""
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(raw).hexdigest()[:8]


def _read_json(path):
    if path == "-":
        raw = sys.stdin.read()
    else:
        with open(path, "r", encoding="utf-8") as handle:
            raw = handle.read()
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise RegistryRefusal("input is not valid JSON: %s" % exc)


def _read_json_file(path):
    with open(path, "r", encoding="utf-8") as handle:
        raw = handle.read()
    try:
        return json.loads(raw)
    except ValueError as exc:
        raise RegistryRefusal("%s is not valid JSON: %s" % (path, exc))


def _parse_json_document(text, source):
    """Parse a JSON document, and name the failure when it does not parse.

    A command may print a note before the document it prints. The note is
    skipped, the document is read.
    """
    raw = text.strip()
    if not raw:
        raise RegistryRefusal("%s is empty" % source)
    try:
        return json.loads(raw)
    except ValueError as exc:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end > start:
            try:
                return json.loads(raw[start : end + 1])
            except ValueError:
                pass
        raise RegistryRefusal("%s is not valid JSON: %s" % (source, exc))


def load_registry(document, source):
    """Extract the host map from a registry document.

    Accepts either the host map itself or a document that carries it under
    the ``DIGICHAT_EMBED_TENANTS`` key.
    """
    if not isinstance(document, dict):
        raise RegistryRefusal("%s: registry must be a JSON object" % source)
    if "DIGICHAT_EMBED_TENANTS" in document:
        document = document["DIGICHAT_EMBED_TENANTS"]
    if not isinstance(document, dict) or not document:
        raise RegistryRefusal("%s: registry carries no tenant entries" % source)
    for host, entry in document.items():
        if not isinstance(entry, dict):
            raise RegistryRefusal("%s: tenant entry %r is not an object" % (source, host))
    return document


def _deep_merge(base, patch):
    """Merge ``patch`` onto ``base``. Keys only in ``base`` are kept."""
    out = copy.deepcopy(base)
    for key, value in patch.items():
        if isinstance(value, dict) and isinstance(out.get(key), dict):
            out[key] = _deep_merge(out[key], value)
        else:
            out[key] = copy.deepcopy(value)
    return out


def _changed_paths(old, new, prefix=""):
    """Paths whose value differs, over the union of both key sets."""
    changed = []
    if isinstance(old, dict) and isinstance(new, dict):
        for key in sorted(set(old) | set(new)):
            path = "%s.%s" % (prefix, key) if prefix else key
            changed += _changed_paths(old.get(key), new.get(key), path)
        return changed
    if old != new:
        changed.append(prefix)
    return changed


def _check_overlay_value(host, value, path, allowed):
    """Every key of an overlay object must be one the runtime reads."""
    for key, sub in value.items():
        full = "%s.%s" % (path, key) if path else key
        if key not in allowed:
            raise RegistryRefusal(
                "overlay entry %r: %s is not a key the runtime reads" % (host, full)
            )
        _check_overlay_shape(host, sub, full)


def _check_overlay_shape(host, value, path):
    """An overlay value must have the shape the runtime reads."""
    if isinstance(value, dict):
        nested = ALLOWED_NESTED_KEYS.get(path)
        if nested is None:
            raise RegistryRefusal(
                "overlay entry %r: %s carries an object; the overlay may not "
                "set nested objects there" % (host, path)
            )
        _check_overlay_value(host, value, path, nested)
    elif isinstance(value, list):
        items = ALLOWED_LIST_ITEM_KEYS.get(path)
        for item in value:
            if isinstance(item, dict):
                if items is None:
                    raise RegistryRefusal(
                        "overlay entry %r: %s carries objects in a list; the "
                        "overlay may not set that" % (host, path)
                    )
                _check_overlay_value(host, item, path, items)
            elif not isinstance(item, str):
                raise RegistryRefusal(
                    "overlay entry %r: %s carries a list item that is not a string" % (host, path)
                )
    elif path in OBJECT_OVERLAY_PATHS:
        # The runtime reads this path as an object. A scalar is a shape
        # mistake, refused by name: without this the merge below raises
        # an AttributeError instead of naming the refusal.
        raise RegistryRefusal(
            "overlay entry %r: %s must be an object, not a %s" % (host, path, type(value).__name__)
        )


def _check_retired_corpus(host, index):
    """The corpus routing is a string, and never the retired corpus."""
    if index is None:
        return
    if not isinstance(index, str):
        raise RegistryRefusal(
            "tenant %r: digisearchIndex must be a string, not a %s" % (host, type(index).__name__)
        )
    for part in index.split(","):
        if part.strip() == FORBIDDEN_INDEX:
            raise RegistryRefusal(
                "tenant %r routes to the retired corpus %r" % (host, FORBIDDEN_INDEX)
            )


def _check_credential_ref(host, name, path):
    """A credential reference must name a secret the runtime can resolve."""
    if not isinstance(name, str) or not name:
        raise RegistryRefusal("tenant %r: %s must name a secret" % (host, path))
    if not CREDENTIAL_REF_PATTERN.match(name):
        raise RegistryRefusal(
            "tenant %r: %s is not a secret name the runtime can resolve "
            "(a capital letter, then capitals, digits and underscores). An "
            "unresolved reference keeps the legacy copy, so the KV write "
            "would have no effect." % (host, path)
        )


def _check_mcp_rows(host, mcp):
    """The MCP rows of a KV entry: references by name, never values."""
    if mcp is None:
        return
    if not isinstance(mcp, dict):
        raise RegistryRefusal(
            "KV registry entry %r: mcp must be an object, not a %s" % (host, type(mcp).__name__)
        )
    servers = mcp.get("servers")
    if servers is None:
        return
    if not isinstance(servers, list):
        raise RegistryRefusal(
            "KV registry entry %r: mcp.servers must be a list, not a %s"
            % (host, type(servers).__name__)
        )
    for server in servers:
        if not isinstance(server, dict):
            raise RegistryRefusal("KV registry entry %r: an mcp server row is not an object" % host)
        # The runtime serves a row that carries a token as it is, so a value
        # here would put a credential in a store that is not the secret
        # store. The rule is the key, not the value: an empty value is a
        # value too.
        if "token" in server:
            raise RegistryRefusal(
                "KV registry entry %r carries an MCP credential value; the "
                "KV copy must hold credential references by name only" % host
            )
        if "tokenEnv" in server:
            _check_credential_ref(host, server.get("tokenEnv"), "mcp.servers[].tokenEnv")


def _credential_refs(composed):
    """The credential references the KV copy depends on. Names, never values.

    The plan prints them, so the operator can check that every secret the
    copy names exists in the Worker: a reference the Worker cannot resolve
    keeps the legacy copy, and the KV write would have no effect.
    """
    refs = []
    for host in sorted(composed):
        entry = composed[host]
        if not isinstance(entry, dict):
            continue
        token_env = entry.get("tokenEnv")
        if isinstance(token_env, str):
            refs.append("%s: %s" % (host, token_env))
        mcp = entry.get("mcp")
        if not isinstance(mcp, dict):
            continue
        servers = mcp.get("servers")
        if not isinstance(servers, list):
            continue
        for server in servers:
            if isinstance(server, dict) and isinstance(server.get("tokenEnv"), str):
                refs.append("%s: mcp %s" % (host, server["tokenEnv"]))
    return refs


def _refuse_occ_model_list(host, source):
    """A raw OCC model id list is still refused. A catalog policy is not."""
    raise RegistryRefusal(
        "%s entry %r carries '%s.available'; DIG-4750 refused an open model id "
        "list for the OCC tenant. A catalog policy (catalog, price cap, presets) "
        "is the 2.6.6 picker. A raw available array is still refused."
        % (source, host, OCC_MODELS_KEY)
    )


def _occ_models_from_overlay(host, overlay_entry, source):
    """Refuse an overlay that tries to set a raw OCC model id list."""
    if host != OCC_HOST or OCC_MODELS_KEY not in overlay_entry:
        return
    models = overlay_entry.get(OCC_MODELS_KEY)
    if isinstance(models, dict) and "available" in models:
        _refuse_occ_model_list(host, source)


def _strip_occ_model_list(host, merged, removed):
    """Drop a raw available list. Keep a catalog policy. Drop an empty section."""
    if host != OCC_HOST or OCC_MODELS_KEY not in merged:
        return
    models = merged.get(OCC_MODELS_KEY)
    if not isinstance(models, dict):
        del merged[OCC_MODELS_KEY]
        removed.append("%s.%s" % (host, OCC_MODELS_KEY))
        return
    if "available" in models:
        del models["available"]
        removed.append("%s.models.available" % host)
    if not models:
        del merged[OCC_MODELS_KEY]
        removed.append("%s.%s" % (host, OCC_MODELS_KEY))


# ---------------------------------------------------------------------------
# Compose
# ---------------------------------------------------------------------------


def compose_registry(live, overlay):
    """Merge the overlay onto the live registry. Returns (composed, report).

    Raises RegistryRefusal when a guard refuses. The composed registry
    keeps every live tenant and every live token.
    """
    if not isinstance(live, dict) or not live:
        raise RegistryRefusal("live registry carries no tenant entries")
    if not isinstance(overlay, dict):
        raise RegistryRefusal("overlay must be a JSON object")

    # Guard 1: the overlay must not carry a tenant the live registry does
    # not have. Such a tenant has no token, so it could not be served.
    new_hosts = sorted(set(overlay) - set(live))
    if new_hosts:
        raise RegistryRefusal(
            "overlay introduces tenant(s) %s that the live registry does not "
            "have; a tenant without a live token cannot be served" % ", ".join(new_hosts)
        )

    composed = {}
    removed = []
    for host, live_entry in live.items():
        if not isinstance(live_entry, dict):
            raise RegistryRefusal("live registry entry %r is not an object" % host)
        token = live_entry.get("token")
        if not isinstance(token, str) or not token:
            raise RegistryRefusal(
                "live registry entry %r has no token; the live registry is "
                "incomplete and cannot be the base of a compose" % host
            )
        live_backend = live_entry.get("backend")
        if live_backend is not None and not isinstance(live_backend, dict):
            raise RegistryRefusal(
                "live registry entry %r: backend must be an object, not a %s"
                % (host, type(live_backend).__name__)
            )
        overlay_entry = overlay.get(host, {})
        if not isinstance(overlay_entry, dict):
            raise RegistryRefusal("overlay entry %r is not an object" % host)

        # Guard 2: the overlay carries no secret.
        for key in sorted(set(overlay_entry) & FORBIDDEN_OVERLAY_KEYS):
            raise RegistryRefusal(
                "overlay entry %r carries %r; %s lives only in the host "
                "secret store, never in the repository" % (host, key, key)
            )

        # Guard 3: every overlay key is one the runtime reads, at the level
        # the runtime reads it.
        unknown = sorted(set(overlay_entry) - ALLOWED_OVERLAY_KEYS - FORBIDDEN_OVERLAY_KEYS)
        if unknown:
            raise RegistryRefusal(
                "overlay entry %r carries unknown key(s) %s; the runtime does "
                "not read them" % (host, ", ".join(unknown))
            )
        _check_overlay_value(host, overlay_entry, "", ALLOWED_OVERLAY_KEYS)

        # Guard 3b: a raw OCC model id list is refused. A catalog policy is not.
        _occ_models_from_overlay(host, overlay_entry, "overlay")

        merged = copy.deepcopy(live_entry)
        for key, value in overlay_entry.items():
            if key == "backend":
                merged["backend"] = _deep_merge(merged.get("backend", {}), value)
            else:
                merged[key] = copy.deepcopy(value)
        # The live token always wins, whatever the overlay said.
        merged["token"] = token
        # A raw available list on the OCC tenant is stripped. A catalog policy
        # stays. The section is removed only when nothing else remains.
        _strip_occ_model_list(host, merged, removed)
        composed[host] = merged

    # Guard 4: no tenant was lost and every tenant has a token.
    lost = sorted(set(live) - set(composed))
    if lost:
        raise RegistryRefusal(
            "compose would drop tenant(s) %s from the live registry" % ", ".join(lost)
        )
    for host, entry in composed.items():
        if not isinstance(entry.get("token"), str) or not entry.get("token"):
            raise RegistryRefusal(
                "composed tenant %r has no token; the runtime refuses a "
                "tenant without a token" % host
            )

    # Guard 5: corpus routing rules.
    #   (a) No tenant may route to the retired corpus.
    #   (b) The overlay may not set the OCC tenant's corpus routing or vault
    #       path. Those live in the host secret store and are set by the
    #       rollout script, never by a repository file, so the composed OCC
    #       entry keeps the live registry's own routing.
    #   (c) The live registry must route the OCC tenant to a corpus. If it
    #       does not, the composed registry would leave that tenant without
    #       one, which is the failure DIG-4488 exists to prevent.
    for host, entry in composed.items():
        backend = entry.get("backend") or {}
        _check_retired_corpus(host, backend.get("digisearchIndex"))
    occ_overlay_backend = (overlay.get(OCC_HOST) or {}).get("backend") or {}
    for key in sorted(set(occ_overlay_backend) & set(OCC_LOCKED_BACKEND_KEYS)):
        raise RegistryRefusal(
            "overlay entry %r may not set %s; the OCC tenant's corpus routing "
            "lives in the host secret store, not in the repository" % (OCC_HOST, key)
        )
    occ_live_backend = (live.get(OCC_HOST) or {}).get("backend") or {}
    if not occ_live_backend.get("digisearchIndex"):
        raise RegistryRefusal(
            "the live registry does not route %r to a corpus; restore the live "
            "registry from the host secret store before composing" % OCC_HOST
        )

    report = {
        "live_hosts": sorted(live),
        "overlay_hosts": sorted(overlay),
        "composed_hosts": sorted(composed),
        "token_lengths": dict((h, len(composed[h]["token"])) for h in composed),
        "changed_paths": [],
        "removed_paths": removed,
    }
    for host in sorted(composed):
        for path in _changed_paths(live.get(host), composed.get(host)):
            report["changed_paths"].append("%s.%s" % (host, path))
    return composed, report


def compose_kv_registry(kv_live, overlay, legacy=None):
    """Compose the Workers KV copy of the tenant registry.

    The KV copy holds credential references by name, never values, and it
    replaces the legacy Worker secret for a host whose references resolve
    (apps/digichat-cloudflare/src/tenants-kv.ts). It is therefore the copy
    that decides what a tenant sees. Returns (composed, report).

    The KV copy keeps the tenants it already has: a tenant that lives only
    in the legacy secret stays there, and the overlay never adds a tenant
    to the KV copy.

    ``legacy`` is the composed legacy registry. When it is given, the
    compose refuses a KV copy that would drop a field the legacy copy
    carries: the runtime replaces the legacy entry for a host, so a field
    that lives only in the legacy copy would stop being served.
    """
    if not isinstance(kv_live, dict) or not kv_live:
        raise RegistryRefusal("the KV registry carries no tenant entries")
    if not isinstance(overlay, dict):
        raise RegistryRefusal("overlay must be a JSON object")
    # Every overlay entry is an object, also for a tenant the KV copy does
    # not have: a shape mistake is named, not raised as an AttributeError.
    for host, entry in overlay.items():
        if not isinstance(entry, dict):
            raise RegistryRefusal("overlay entry %r is not an object" % host)

    composed = {}
    removed = []
    for host, base_entry in kv_live.items():
        if not isinstance(base_entry, dict):
            raise RegistryRefusal("KV registry entry %r is not an object" % host)
        # The KV copy holds references by name. A value here would put a
        # credential in a store that is not the secret store.
        if "token" in base_entry:
            raise RegistryRefusal(
                "KV registry entry %r carries a token value; the KV copy must "
                "hold credential references by name only" % host
            )
        # Every KV host must carry a credential reference. The runtime
        # replaces the legacy entry with the KV entry when the references
        # resolve, so a KV entry without a reference serves a tenant that
        # has no token, and the container refuses the whole registry: not
        # only that tenant, every tenant.
        if "tokenEnv" not in base_entry:
            raise RegistryRefusal(
                "KV registry entry %r carries no credential reference; add a "
                "tokenEnv before writing the KV copy, or the tenant is served "
                "without its token and the whole registry is refused" % host
            )
        _check_credential_ref(host, base_entry.get("tokenEnv"), "tokenEnv")
        _check_mcp_rows(host, base_entry.get("mcp"))
        base_backend = base_entry.get("backend")
        if base_backend is not None and not isinstance(base_backend, dict):
            raise RegistryRefusal(
                "KV registry entry %r: backend must be an object, not a %s"
                % (host, type(base_backend).__name__)
            )
        overlay_entry = overlay.get(host, {})
        if not isinstance(overlay_entry, dict):
            raise RegistryRefusal("overlay entry %r is not an object" % host)

        # Guard 1: the overlay carries no secret.
        for key in sorted(set(overlay_entry) & FORBIDDEN_OVERLAY_KEYS):
            raise RegistryRefusal(
                "overlay entry %r carries %r; %s lives only in the host "
                "secret store, never in the repository" % (host, key, key)
            )

        # Guard 2: every overlay key is one the runtime reads, at the level
        # the runtime reads it.
        unknown = sorted(set(overlay_entry) - ALLOWED_OVERLAY_KEYS - FORBIDDEN_OVERLAY_KEYS)
        if unknown:
            raise RegistryRefusal(
                "overlay entry %r carries unknown key(s) %s; the runtime does "
                "not read them" % (host, ", ".join(unknown))
            )
        _check_overlay_value(host, overlay_entry, "", ALLOWED_OVERLAY_KEYS)

        # Guard 3: a raw OCC model id list is refused. A catalog policy is not.
        _occ_models_from_overlay(host, overlay_entry, "overlay")

        merged = copy.deepcopy(base_entry)
        for key, value in overlay_entry.items():
            if key == "backend":
                merged["backend"] = _deep_merge(merged.get("backend", {}), value)
            else:
                merged[key] = copy.deepcopy(value)
        # The KV copy is the one that is served. Strip a raw available list.
        # Keep a catalog policy. Drop the section only when it is empty.
        _strip_occ_model_list(host, merged, removed)
        # Guard 5: the KV copy replaces the legacy entry for a host, so a
        # field that lives only in the legacy copy stops being served the
        # moment the KV copy is written. The plan would not show it, and the
        # tenant would lose it without a word.
        if isinstance(legacy, dict):
            legacy_entry = legacy.get(host)
            if isinstance(legacy_entry, dict):
                dropped = sorted(set(legacy_entry) - set(merged) - KV_DROP_ALLOWED)
                if dropped:
                    raise RegistryRefusal(
                        "the KV copy for %r would drop %s, which the legacy copy "
                        "carries. The KV copy replaces the legacy entry for a "
                        "tenant whose references resolve, so those fields would "
                        "stop being served." % (host, ", ".join(dropped))
                    )
        composed[host] = merged

    # Guard 4: corpus routing rules, as in the legacy compose.
    for host, entry in composed.items():
        backend = entry.get("backend") or {}
        _check_retired_corpus(host, backend.get("digisearchIndex"))
    occ_overlay_entry = overlay.get(OCC_HOST) or {}
    occ_overlay_backend = occ_overlay_entry.get("backend") or {}
    if not isinstance(occ_overlay_backend, dict):
        raise RegistryRefusal(
            "overlay entry %r: backend must be an object, not a %s"
            % (OCC_HOST, type(occ_overlay_backend).__name__)
        )
    for key in sorted(set(occ_overlay_backend) & set(OCC_LOCKED_BACKEND_KEYS)):
        raise RegistryRefusal(
            "overlay entry %r may not set %s; the OCC tenant's corpus routing "
            "lives in the host secret store, not in the repository" % (OCC_HOST, key)
        )
    occ_base_entry = kv_live.get(OCC_HOST) or {}
    occ_base_backend = occ_base_entry.get("backend") or {}
    if not occ_base_backend.get("digisearchIndex"):
        raise RegistryRefusal(
            "the KV registry does not route %r to a corpus; restore the KV "
            "copy from the host secret store before composing" % OCC_HOST
        )

    report = {
        "kv_hosts": sorted(kv_live),
        "overlay_hosts": sorted(overlay),
        "composed_hosts": sorted(composed),
        "hosts_only_in_overlay": sorted(set(overlay) - set(kv_live)),
        "changed_paths": [],
        "removed_paths": removed,
        "credential_refs": _credential_refs(composed),
    }
    for host in sorted(composed):
        for path in _changed_paths(kv_live.get(host), composed.get(host)):
            report["changed_paths"].append("%s.%s" % (host, path))
    return composed, report


# ---------------------------------------------------------------------------
# Plan
# ---------------------------------------------------------------------------


def render_plan(composed, report, live_source, overlay_source):
    lines = []
    lines.append("digichat tenant registry: compose plan")
    lines.append("  live registry : %s" % live_source)
    lines.append("  overlay       : %s" % overlay_source)
    lines.append("  tenants in live registry : %s" % ", ".join(report["live_hosts"]))
    lines.append(
        "  tenants in overlay       : %s" % (", ".join(report["overlay_hosts"]) or "(none)")
    )
    lines.append("  tenants after compose    : %s" % ", ".join(report["composed_hosts"]))
    lengths = report["token_lengths"]
    lines.append(
        "  token length per tenant (live value kept) : %s"
        % ", ".join("%s=%d" % (h, lengths[h]) for h in sorted(lengths))
    )
    changed = report["changed_paths"]
    lines.append("  changed paths (%d):" % len(changed))
    for path in changed:
        lines.append("    %s" % path)
    if not changed:
        lines.append("    (none; the overlay changes nothing)")
    removed = report["removed_paths"]
    lines.append("  removed paths (%d):" % len(removed))
    for path in removed:
        lines.append("    %s" % path)
    if not removed:
        lines.append("    (none)")
    lines.append("  composed registry fingerprint : sha256:%s" % fingerprint(composed))
    lines.append(
        "  note: this is the legacy copy. For a tenant whose KV credential "
        "references resolve, the KV copy is the one that is served; pass "
        "--kv-from to plan the KV copy as well."
    )
    return "\n".join(lines)


def render_kv_plan(composed, report, kv_source, overlay_source, key, namespace_id):
    lines = []
    lines.append("digichat tenant registry: KV copy plan")
    lines.append("  KV source      : %s" % kv_source)
    lines.append("  overlay        : %s" % overlay_source)
    lines.append("  KV key         : %s" % key)
    lines.append("  KV namespace   : %s" % (namespace_id or "(unknown)"))
    lines.append("  tenants in the KV copy : %s" % ", ".join(report["kv_hosts"]))
    lines.append("  tenants after compose  : %s" % ", ".join(report["composed_hosts"]))
    only = report["hosts_only_in_overlay"]
    lines.append(
        "  tenants only in the overlay (not added to the KV copy) : %s"
        % (", ".join(only) or "(none)")
    )
    changed = report["changed_paths"]
    lines.append("  changed paths (%d):" % len(changed))
    for path in changed:
        lines.append("    %s" % path)
    if not changed:
        lines.append("    (none; the overlay changes nothing in the KV copy)")
    removed = report["removed_paths"]
    lines.append("  removed paths (%d):" % len(removed))
    for path in removed:
        lines.append("    %s" % path)
    if not removed:
        lines.append("    (none)")
    lines.append("  composed KV fingerprint : sha256:%s" % fingerprint(composed))
    refs = report.get("credential_refs") or []
    lines.append("  credential references the KV copy needs (names, not values):")
    for ref in refs:
        lines.append("    %s" % ref)
    if not refs:
        lines.append("    (none)")
    lines.append(
        "  note: for a tenant whose KV credential references resolve, this "
        "copy wins over the legacy secret. A tenant whose references do not "
        "resolve keeps the legacy copy, and the KV write has no effect for it."
    )
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def _git_toplevel(cwd=None):
    """The top level of the git checkout that holds ``cwd``.

    Returns None when there is no git, no checkout there, or the answer
    cannot be resolved. The answer is resolved on both sides, so a
    symlinked spelling of a checkout still names the same tree.
    """
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    root = out.stdout.strip()
    if not root:
        return None
    return os.path.realpath(root)


def repo_root():
    """The repository that OWNS this tool, resolved.

    The guard is about the checkout this script ships in, so the root
    comes from the script's own directory and never from the caller's
    working directory. Returns None when it cannot be resolved; the
    caller must then refuse to write, because an unknown root cannot
    contain anything.
    """
    return _git_toplevel(SCRIPT_DIR)


def cwd_repo_root():
    """The repository of the working directory, resolved, or None.

    A second root the guard covers: the operator may be standing in
    another checkout, and the registry carries tenant tokens, so it must
    not land in that one either.
    """
    return _git_toplevel(None)


def _is_inside(root, path):
    """True when path is the root itself or sits under it."""
    return path == root or path.startswith(root + os.sep)


def write_out(composed, out_path):
    """Write the composed registry. Refuses to write inside a repository."""
    root = repo_root()
    if not root:
        raise RegistryRefusal(
            "refusing to write the composed registry: the repository root "
            "could not be resolved, so the guard cannot prove the target is "
            "outside the repository"
        )
    root = os.path.realpath(root)
    roots = [root]
    other = cwd_repo_root()
    if other:
        other = os.path.realpath(other)
        if other != root:
            roots.append(other)
    # Both sides are resolved before they are compared. A symlinked
    # spelling of the repository otherwise slips past the prefix test and
    # the token-bearing registry lands inside the checkout. The literal
    # path is checked as well: a path spelled inside the repository is
    # refused even when it is a symlink pointing out of it, because
    # writing it would replace that symlink with a regular file inside
    # the checkout.
    target = os.path.abspath(out_path)
    resolved = os.path.realpath(target)
    for candidate in roots:
        if _is_inside(candidate, resolved) or _is_inside(candidate, target):
            raise RegistryRefusal(
                "refusing to write the composed registry inside the repository "
                "(%s): it carries tenant tokens" % candidate
            )
    directory = os.path.dirname(target) or "."
    handle, temp = tempfile.mkstemp(dir=directory, prefix=".digichat-registry-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(composed, out, indent=2, sort_keys=True)
            out.write("\n")
        os.chmod(temp, 0o600)
        os.replace(temp, target)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return target


# ---------------------------------------------------------------------------
# Apply
# ---------------------------------------------------------------------------


def _run(argv, cwd=None, stdin_text=None):
    proc = subprocess.run(
        argv,
        cwd=cwd,
        input=stdin_text,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        universal_newlines=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def _run_read(argv, cwd=None):
    """Run a command and keep stdout and stderr apart.

    The live KV read parses stdout as JSON. A note from wrangler or from
    npm (npm prints one the first time it installs the package) lands on
    stderr, and the two streams must not mix here: the merged blob is not
    a document.
    """
    proc = subprocess.run(
        argv,
        cwd=cwd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        universal_newlines=True,
        check=False,
    )
    return proc.returncode, proc.stdout, proc.stderr


def secret_put(worker, secret_name, payload, wrangler_cmd, worker_dir):
    """Write the Worker secret. The value goes on stdin, never in argv."""
    argv = list(wrangler_cmd) + ["secret", "put", secret_name, "--name", worker]
    code, out = _run(argv, cwd=worker_dir, stdin_text=payload)
    return code, out


def _config_blocks(lines):
    """The [[table]] blocks of a worker config file, as flat key/value maps."""
    blocks = []
    current = None
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[["):
            current = {"__header__": stripped}
            blocks.append(current)
            continue
        if stripped.startswith("[") and stripped.endswith("]"):
            # A plain [table] ends the current block.
            current = None
            continue
        if current is None or "=" not in stripped:
            continue
        key, _, value = stripped.partition("=")
        current[key.strip()] = value.strip().strip('"').strip("'")
    return blocks


def kv_namespace_id(worker_dir, binding=KV_BINDING):
    """The id of the KV namespace bound to ``binding``, read from the worker config.

    Returns None when the config cannot be read or does not bind the
    namespace: the caller then refuses, because an unknown namespace id
    cannot be written to.
    """
    path = os.path.join(worker_dir, KV_CONFIG_FILE)
    try:
        with open(path, "r", encoding="utf-8") as handle:
            lines = handle.readlines()
    except OSError:
        return None
    for block in _config_blocks(lines):
        if block.get("__header__") == "[[kv_namespaces]]" and block.get("binding") == binding:
            return block.get("id")
    return None


def kv_key_get(key, namespace_id, wrangler_cmd, worker_dir):
    """Read the live KV copy of the registry. Read only.

    Returns (code, stdout, stderr). The caller parses stdout.
    """
    argv = list(wrangler_cmd) + [
        "kv",
        "key",
        "get",
        key,
        "--namespace-id",
        namespace_id,
        "--remote",
        "--text",
    ]
    return _run_read(argv, cwd=worker_dir)


def write_temp_json(document):
    """Write a JSON document to a private temporary file. Returns the path."""
    handle, temp = tempfile.mkstemp(prefix="digichat-tenants-kv-")
    try:
        with os.fdopen(handle, "w", encoding="utf-8") as out:
            json.dump(document, out, indent=2, sort_keys=True)
            out.write("\n")
        os.chmod(temp, 0o600)
    except OSError:
        os.unlink(temp)
        raise
    return temp


def kv_key_put(key, namespace_id, document_path, wrangler_cmd, worker_dir):
    """Write the composed KV copy. The document travels as a file, not as a value."""
    argv = list(wrangler_cmd) + [
        "kv",
        "key",
        "put",
        key,
        "--namespace-id",
        namespace_id,
        "--path",
        document_path,
        "--remote",
    ]
    return _run(argv, cwd=worker_dir)


def _restore_kv_copy(key, namespace_id, document, wrangler_cmd, worker_dir):
    """Put the previous KV document back. Best effort.

    Used when the legacy secret write fails after the KV copy was written:
    the two copies must never disagree about a tenant. Returns True when the
    previous document is live again.
    """
    temp = None
    try:
        temp = write_temp_json(document)
        code, _out = kv_key_put(key, namespace_id, temp, wrangler_cmd, worker_dir)
    except OSError:
        return False
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    return code == 0


def recycle_container(admin_key_file, reset_url):
    """Recycle the digichat container so it reads the new registry at boot.

    The admin key is a credential. It is handed to curl on stdin, as a
    header line, never in the argument list: an argument list is
    readable by every local process through ps, a pipe is not. The
    sibling secret_put already sends its value on stdin.
    """
    try:
        with open(admin_key_file, "r", encoding="utf-8") as handle:
            key = handle.read().strip()
    except OSError as exc:
        raise RegistryRefusal("cannot read the admin key file: %s" % exc)
    if not key:
        raise RegistryRefusal("the admin key file is empty")
    if "\n" in key or "\r" in key:
        raise RegistryRefusal("the admin key file holds more than one line")
    argv = [
        "curl",
        "-sS",
        "-o",
        "-",
        "-w",
        "\nhttp_code=%{http_code}\n",
        "-X",
        "POST",
        reset_url,
        # "-H @-" reads the header from stdin, so the value never
        # becomes a command line argument.
        "-H",
        "@-",
    ]
    code, out = _run(argv, stdin_text="x-digi-admin-key: " + key + "\n")
    body = "\n".join(line for line in out.splitlines() if not line.startswith("http_code="))
    status = ""
    for line in out.splitlines():
        if line.startswith("http_code="):
            status = line.split("=", 1)[1]
    return code, status, body.strip()


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _load_live(args):
    source = args.live_from
    if source is None:
        source = os.environ.get("DIGICHAT_EMBED_TENANTS_LIVE_FILE") or DEFAULT_LIVE_FILE
    if source == "-":
        document = _read_json("-")
    else:
        document = _read_json_file(source)
    return source, load_registry(document, source)


def _load_overlay(args):
    source = args.overlay
    document = _read_json_file(source)
    return source, load_registry(document, source)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command")
    sub.required = True

    for name in ("compose", "apply"):
        cmd = sub.add_parser(name)
        cmd.add_argument(
            "--live-from",
            default=None,
            help="live registry file, or - for stdin (default: the host secret store copy)",
        )
        cmd.add_argument(
            "--overlay",
            required=True,
            help="overlay file (a tenant map, or a document with a DIGICHAT_EMBED_TENANTS key)",
        )
        cmd.add_argument(
            "--out",
            default=None,
            help="write the composed registry to this path (refused inside the repository)",
        )
        cmd.add_argument(
            "--plan-only", action="store_true", help="print the plan and write nothing"
        )
        cmd.add_argument(
            "--kv-from",
            default=None,
            help="live KV copy of the registry to compose from (a file)",
        )
        cmd.add_argument(
            "--kv-out",
            default=None,
            help="write the composed KV registry to this path (refused inside the repository)",
        )
        cmd.add_argument("--kv-key", default=KV_KEY, help="KV key that holds the registry")
        cmd.add_argument(
            "--kv-namespace-id",
            default=None,
            help="KV namespace id (default: read from the worker config)",
        )
        cmd.add_argument(
            "--worker-dir",
            default=DEFAULT_WORKER_DIR,
            help="worker directory that holds the worker config",
        )
        cmd.add_argument(
            "--wrangler-cmd",
            default=DEFAULT_WRANGLER_CMD,
            help="wrangler command, split on spaces",
        )

    apply_cmd = sub.choices["apply"]
    apply_cmd.add_argument("--worker", default=DEFAULT_WORKER)
    apply_cmd.add_argument("--secret-name", default=SECRET_NAME)
    apply_cmd.add_argument("--admin-key-file", default=DEFAULT_ADMIN_KEY_FILE)
    apply_cmd.add_argument("--reset-url", default=RESET_URL)
    apply_cmd.add_argument(
        "--confirm", default=None, help="typed confirmation word (%s)" % APPLY_CONFIRM_WORD
    )
    apply_cmd.add_argument(
        "--dry-run", action="store_true", help="print the plan and the commands, write nothing"
    )

    args = parser.parse_args(argv)

    try:
        live_source, live = _load_live(args)
        overlay_source, overlay = _load_overlay(args)
        composed, report = compose_registry(live, overlay)
    except RegistryRefusal as refusal:
        sys.stderr.write("REFUSED: %s\n" % refusal)
        return 2

    print(render_plan(composed, report, live_source, overlay_source))

    wrangler_cmd = args.wrangler_cmd.split()
    namespace_id = args.kv_namespace_id or kv_namespace_id(args.worker_dir)

    # The KV copy. For a tenant whose credential references resolve it wins
    # over the legacy secret, so it is the copy that decides what the tenant
    # sees. The apply reads it live; a plan reads it from a file, so the
    # plan stays offline.
    kv_source = None
    kv_live = None
    kv_from_document = None
    if args.kv_from:
        try:
            kv_from_document = load_registry(_read_json_file(args.kv_from), args.kv_from)
        except RegistryRefusal as refusal:
            sys.stderr.write("REFUSED: %s\n" % refusal)
            return 2
    if args.command == "apply":
        # The apply always reads the live KV copy. The write replaces the
        # whole document, so a copy read earlier would drop every tenant
        # another operator added since.
        if not namespace_id:
            sys.stderr.write("REFUSED: the KV namespace id is unknown; pass --kv-namespace-id.\n")
            return 2
        code, out, _err = kv_key_get(args.kv_key, namespace_id, wrangler_cmd, args.worker_dir)
        if code != 0:
            sys.stderr.write(
                "REFUSED: the live KV copy could not be read, so the copy that "
                "decides what the OCC tenant sees cannot be composed. Nothing "
                "was written.\n"
            )
            return 2
        try:
            kv_live = load_registry(
                _parse_json_document(out, "the live KV copy"), "the live KV copy"
            )
        except RegistryRefusal as refusal:
            sys.stderr.write(
                "REFUSED: the live KV copy is not a readable registry (%s). "
                "Nothing was written.\n" % refusal
            )
            return 2
        kv_source = "the live KV key %s in the namespace %s" % (args.kv_key, namespace_id)
        if kv_from_document is not None:
            # The file is a copy of the live KV copy. A copy that names other
            # tenants is stale, and writing it would drop them.
            if sorted(kv_from_document) != sorted(kv_live):
                sys.stderr.write(
                    "REFUSED: the KV copy in %s does not match the live KV copy "
                    "(%s). A stale copy would drop the tenants it does not name. "
                    "Nothing was written.\n" % (args.kv_from, ", ".join(sorted(kv_live)))
                )
                return 2
            kv_source = "%s (the copy in %s matches it)" % (kv_source, args.kv_from)
    elif kv_from_document is not None:
        kv_live = kv_from_document
        kv_source = args.kv_from

    kv_composed = None
    if kv_live is not None:
        try:
            kv_composed, kv_report = compose_kv_registry(kv_live, overlay, legacy=composed)
        except RegistryRefusal as refusal:
            sys.stderr.write("REFUSED: %s\n" % refusal)
            return 2
        print(
            render_kv_plan(
                kv_composed, kv_report, kv_source, overlay_source, args.kv_key, namespace_id
            )
        )
    else:
        print(
            "digichat tenant registry: the KV copy was not composed. Pass "
            "--kv-from <file> to plan it. For a tenant whose KV credential "
            "references resolve, the KV copy is the one that is served, so a "
            "plan without it does not show what the tenant sees."
        )

    if args.plan_only:
        print("plan only: nothing was written and the container was not recycled")
        return 0

    if args.out:
        try:
            written = write_out(composed, args.out)
        except RegistryRefusal as refusal:
            sys.stderr.write("REFUSED: %s\n" % refusal)
            return 2
        print("composed registry written to %s (mode 0600)" % written)

    if args.kv_out and kv_composed is not None:
        try:
            written = write_out(kv_composed, args.kv_out)
        except RegistryRefusal as refusal:
            sys.stderr.write("REFUSED: %s\n" % refusal)
            return 2
        print("composed KV registry written to %s (mode 0600)" % written)

    if args.command != "apply":
        return 0

    if kv_composed is None:
        sys.stderr.write(
            "REFUSED: the KV copy is not composed, so the copy that decides "
            "what the OCC tenant sees would not be written. Nothing was "
            "written.\n"
        )
        return 2

    if not namespace_id:
        sys.stderr.write(
            "REFUSED: the KV namespace id is unknown; pass --kv-namespace-id. "
            "Nothing was written.\n"
        )
        return 2

    payload = json.dumps(composed, indent=2, sort_keys=True)

    if args.dry_run:
        # The secret NAME is not printed and the command output is never
        # echoed: both can carry secret-derived text into a log.
        print("dry run: nothing was written, the container was not recycled")
        print("would write the KV key %s in the namespace %s" % (args.kv_key, namespace_id))
        print("would write the worker secret to the worker %s" % args.worker)
        print("would recycle the container with POST %s" % args.reset_url)
        return 0

    if args.confirm != APPLY_CONFIRM_WORD:
        sys.stderr.write(
            "Type %s to write the KV key %s and the registry secret to the "
            "worker %s.\n" % (APPLY_CONFIRM_WORD, args.kv_key, args.worker)
        )
        typed = sys.stdin.readline().strip()
        if typed != APPLY_CONFIRM_WORD:
            sys.stderr.write("confirmation not given. Nothing was written.\n")
            return 2

    # The KV copy first. It is the copy that is served for a tenant whose
    # credential references resolve, so when it fails the legacy copy is
    # left alone: the two copies must never disagree about the OCC tenant.
    temp = None
    try:
        temp = write_temp_json(kv_composed)
        code, out = kv_key_put(args.kv_key, namespace_id, temp, wrangler_cmd, args.worker_dir)
    finally:
        if temp and os.path.exists(temp):
            os.unlink(temp)
    if code != 0:
        sys.stderr.write(
            "the KV write failed. The legacy secret was not written and the "
            "container was not recycled.\n"
        )
        # The KV copy holds no credential value, so what the command printed
        # carries no secret. It is printed to name the failure.
        sys.stderr.write(out)
        return 1
    print("the KV key %s was written in the namespace %s" % (args.kv_key, namespace_id))

    code, _out = secret_put(args.worker, args.secret_name, payload, wrangler_cmd, args.worker_dir)
    if code != 0:
        # Nothing the command produced is logged, not even its exit code:
        # the command was handed the registry, so its output and its status
        # are secret-derived text. Re-run it in your own terminal to read
        # the error.
        sys.stderr.write(
            "the registry write failed. The container was not recycled. "
            "Nothing from the command is printed, so no credential can reach "
            "the log; re-run the command in your own terminal to read the "
            "error.\n"
        )
        # The KV copy is already live. Put the previous document back, so
        # the two copies do not disagree about the OCC tenant.
        restored = _restore_kv_copy(
            args.kv_key, namespace_id, kv_live, wrangler_cmd, args.worker_dir
        )
        if restored:
            sys.stderr.write(
                "the previous KV copy was put back, so the live KV copy and the "
                "legacy secret still agree.\n"
            )
        else:
            sys.stderr.write(
                "the previous KV copy was NOT put back, so the live KV copy and "
                "the legacy secret now disagree. Restore the KV copy from the "
                "host secret store before the next apply.\n"
            )
        return 1
    print("the worker secret was written to the worker %s" % args.worker)

    try:
        rcode, status, body = recycle_container(args.admin_key_file, args.reset_url)
    except RegistryRefusal as refusal:
        sys.stderr.write("the secret is written but the container was NOT recycled: %s\n" % refusal)
        return 1
    print("container recycle: http %s" % (status or "?"))
    if body:
        print("container recycle response: %s" % body)
    if rcode != 0 or status != "200":
        sys.stderr.write(
            "the container recycle did not answer 200. The old "
            "container may still hold the old registry.\n"
        )
        return 1
    print("registry applied. tenants: %s" % ", ".join(report["composed_hosts"]))
    return 0


if __name__ == "__main__":
    sys.exit(main())
