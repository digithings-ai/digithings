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

Usage
-----

Plan only (offline, prints no secret value):

    python3 scripts/digichat_tenant_registry.py compose \
        --live-from ~/.config/digithings/secrets/digichat-embed-tenants.deploy.json \
        --overlay infra/digichat-release/DIG-3556-staged-prod-tenant-config.json

Write the Worker secret and recycle the container:

    python3 scripts/digichat_tenant_registry.py apply \
        --live-from <host-store-file> \
        --overlay infra/digichat-release/DIG-3556-staged-prod-tenant-config.json

The apply path needs Cloudflare credentials for ``wrangler secret put``
and the digichat admin key for the container reset. It prints a plan and
asks for a typed confirmation before it writes anything.
"""

import argparse
import copy
import hashlib
import json
import os
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
    "models": frozenset(["default", "available", "allowPicker"]),
    "tools": frozenset(["allowUserToggle", "catalog"]),
    "tools.catalog": frozenset(["id", "default", "label", "tools"]),
}

# Keys allowed for the objects inside a list.
ALLOWED_LIST_ITEM_KEYS = {
    "tools.catalog": frozenset(["id", "default", "label", "tools"]),
    "tools.catalog.tools": frozenset(["id", "label"]),
}

# The OCC corpus index. The retired OCC ticket corpus must never be routed
# to (scripts/occ_invite_key_write.sh enforces the same rule).
OCC_HOST = "occ.digithings.ai"
OCC_INDEX = "occ_help"
FORBIDDEN_INDEX = "occ_tickets"

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
    for host, live_entry in live.items():
        if not isinstance(live_entry, dict):
            raise RegistryRefusal("live registry entry %r is not an object" % host)
        token = live_entry.get("token")
        if not isinstance(token, str) or not token:
            raise RegistryRefusal(
                "live registry entry %r has no token; the live registry is "
                "incomplete and cannot be the base of a compose" % host
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

        merged = copy.deepcopy(live_entry)
        for key, value in overlay_entry.items():
            if key == "backend":
                merged["backend"] = _deep_merge(merged.get("backend", {}), value)
            else:
                merged[key] = copy.deepcopy(value)
        # The live token always wins, whatever the overlay said.
        merged["token"] = token
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
    for host, entry in composed.items():
        backend = entry.get("backend") or {}
        index = backend.get("digisearchIndex")
        if index == FORBIDDEN_INDEX:
            raise RegistryRefusal(
                "tenant %r routes to the retired corpus %r" % (host, FORBIDDEN_INDEX)
            )
        if host == OCC_HOST and index is not None and index != OCC_INDEX:
            raise RegistryRefusal("tenant %r must route to %r, not %r" % (host, OCC_INDEX, index))

    report = {
        "live_hosts": sorted(live),
        "overlay_hosts": sorted(overlay),
        "composed_hosts": sorted(composed),
        "token_lengths": dict((h, len(composed[h]["token"])) for h in composed),
        "changed_paths": [],
    }
    for host in sorted(composed):
        for path in _changed_paths(live.get(host), composed.get(host)):
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
    lines.append("  composed registry fingerprint : sha256:%s" % fingerprint(composed))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def repo_root():
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            universal_newlines=True,
            check=False,
        )
    except OSError:
        return None
    if out.returncode != 0:
        return None
    return out.stdout.strip() or None


def write_out(composed, out_path):
    """Write the composed registry. Refuses to write inside the repository."""
    root = repo_root()
    target = os.path.abspath(out_path)
    if root and (target == root or target.startswith(root + os.sep)):
        raise RegistryRefusal(
            "refusing to write the composed registry inside the repository "
            "(%s): it carries tenant tokens" % root
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


def secret_put(worker, secret_name, payload, wrangler_cmd, worker_dir):
    """Write the Worker secret. The value goes on stdin, never in argv."""
    argv = list(wrangler_cmd) + ["secret", "put", secret_name, "--name", worker]
    code, out = _run(argv, cwd=worker_dir, stdin_text=payload)
    return code, out


def recycle_container(admin_key_file, reset_url):
    """Recycle the digichat container so it reads the new registry at boot."""
    try:
        with open(admin_key_file, "r", encoding="utf-8") as handle:
            key = handle.read().strip()
    except OSError as exc:
        raise RegistryRefusal("cannot read the admin key file: %s" % exc)
    if not key:
        raise RegistryRefusal("the admin key file is empty")
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
        "-H",
        "x-digi-admin-key: " + key,
    ]
    code, out = _run(argv)
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

    apply_cmd = sub.choices["apply"]
    apply_cmd.add_argument("--worker", default=DEFAULT_WORKER)
    apply_cmd.add_argument("--secret-name", default=SECRET_NAME)
    apply_cmd.add_argument("--admin-key-file", default=DEFAULT_ADMIN_KEY_FILE)
    apply_cmd.add_argument("--reset-url", default=RESET_URL)
    apply_cmd.add_argument("--worker-dir", default="apps/digichat-cloudflare")
    apply_cmd.add_argument(
        "--wrangler-cmd",
        default="npx --yes wrangler@4.133.0",
        help="wrangler command, split on spaces",
    )
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

    if args.out and not args.plan_only:
        try:
            written = write_out(composed, args.out)
        except RegistryRefusal as refusal:
            sys.stderr.write("REFUSED: %s\n" % refusal)
            return 2
        print("composed registry written to %s (mode 0600)" % written)

    if args.command != "apply":
        return 0

    payload = json.dumps(composed, indent=2, sort_keys=True)
    wrangler_cmd = args.wrangler_cmd.split()

    if args.dry_run:
        print("dry run: no secret was written, the container was not recycled")
        print("would write the secret %s to the worker %s" % (args.secret_name, args.worker))
        print("would recycle the container with POST %s" % args.reset_url)
        return 0

    if args.confirm != APPLY_CONFIRM_WORD:
        sys.stderr.write(
            "Type %s to write the registry secret to the worker %s.\n"
            % (APPLY_CONFIRM_WORD, args.worker)
        )
        typed = sys.stdin.readline().strip()
        if typed != APPLY_CONFIRM_WORD:
            sys.stderr.write("confirmation not given. Nothing was written.\n")
            return 2

    code, out = secret_put(args.worker, args.secret_name, payload, wrangler_cmd, args.worker_dir)
    if code != 0:
        sys.stderr.write(
            "the secret write failed (rc=%d). The container was not recycled.\n%s\n" % (code, out)
        )
        return 1
    print("secret %s written to the worker %s" % (args.secret_name, args.worker))

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
