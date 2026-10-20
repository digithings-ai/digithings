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
        index = backend.get("digisearchIndex")
        if index == FORBIDDEN_INDEX:
            raise RegistryRefusal(
                "tenant %r routes to the retired corpus %r" % (host, FORBIDDEN_INDEX)
            )
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


def secret_put(worker, secret_name, payload, wrangler_cmd, worker_dir):
    """Write the Worker secret. The value goes on stdin, never in argv."""
    argv = list(wrangler_cmd) + ["secret", "put", secret_name, "--name", worker]
    code, out = _run(argv, cwd=worker_dir, stdin_text=payload)
    return code, out


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
        # The secret NAME is not printed and the command output is never
        # echoed: both can carry secret-derived text into a log.
        print("dry run: no secret was written, the container was not recycled")
        print("would write the worker secret to the worker %s" % args.worker)
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
