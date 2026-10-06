#!/usr/bin/env python3
"""
Check that scripts/occ_invite_key_rollout.sh refuses to run on an unauthenticated
wrangler, and never reports an unreadable secret list as a missing secret.

Why this exists
---------------
The 2026-10-06 rollout attempt died with:

    Not logged in. Your auth token has expired and could not be refreshed...

    FATAL: DIGICHAT_EMBED_TENANTS is not set on this Worker. Stop and read the
    runbook: Act B1 changes a field inside the existing registry, it does not
    create the secret. Nothing was written.

That second line was false. Two independent defects combined to produce it:

  1. The auth-failure patterns did not include wrangler's expired-token wording
     ("Not logged in", "auth token has expired"), so the guard did not fire.
  2. The positive identity pattern `*"logged in"*` matched the substring inside
     "Not logged in", so the script reported a CONFIRMED identity for a token
     that had just been rejected.

The `secret list` call then failed with the same text, and its failure patterns
missed it too, so an unreadable list fell through to the "secret is absent"
branch. The dangerous direction is the fall-through: an operator who believes the
secret is missing will create it, overwriting the live OCC tenant registry that
holds branding, backend config, digisearch indexes and vault prefixes.

Fails if the guard regresses. Never touches the network, Cloudflare, or a secret:
`wrangler` is a shell function wrapping `npx`, so the stub replaces `npx` on PATH.
"""
import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
ROLLOUT = REPO_ROOT / "scripts" / "occ_invite_key_rollout.sh"

# Verbatim from the 2026-10-06 failure. The substring "logged in" occurs inside
# "Not logged in", which is the whole point of the check.
EXPIRED_TOKEN = (
    " \u26a1\ufe0f wrangler 4.133.0\n"
    "\n"
    "Getting User settings...\n"
    "\n"
    " \u2718 [ERROR] Not logged in. Your auth token has expired and could not be "
    "refreshed, and the environment is non-interactive. Run `wrangler login` in an "
    "interactive terminal or set a CLOUDFLARE_API_TOKEN.\n"
)
NOT_AUTHENTICATED = (
    " \u2718 [ERROR] You are not authenticated. Please run `wrangler login`.\n"
)
LOGGED_IN = (
    " \u26a1\ufe0f wrangler 4.133.0\n"
    "\n"
    "Getting User settings...\n"
    "\n"
    " \u2718 [ERROR] Provide a valid API Token.\n"
)

SECRET_LIST_WITH = (
    "┌──────────────────────┬────────────┐\n"
    "│ name                │ type       │\n"
    "├──────────────────────┼────────────┤\n"
    "│ DIGICHAT_EMBED_TENANTS │ secret_text │\n"
    "│ DIGICHAT_EMBED_HOSTS   │ secret_text │\n"
    "└──────────────────────┴────────────┘\n"
)
SECRET_LIST_WITHOUT = SECRET_LIST_WITH.replace("DIGICHAT_EMBED_TENANTS ", "OTHER_SECRET_NAME  ")

# Any wrangler subcommand that would change production. The guard must run before
# the first of these; a test that reaches one is a test failure, not a warning.
MUTATING = ("deploy", "secret put", "versions", "publish", "secret delete")

NPX_STUB = r"""#!/usr/bin/env bash
# Records every invocation, then answers from the scenario env vars.
printf '%s\n' "$*" >> "$WRANGLER_CALL_LOG"
args="$*"
case "$args" in
  *whoami*)
    case "$STUB_AUTH" in
      expired)            printf '%s' "$STUB_EXPIRED" ; exit 1 ;;
      not_authenticated)  printf '%s' "$STUB_NOTAUTH" ; exit 1 ;;
      bad_token)          printf '%s' "$STUB_BADTOKEN" ; exit 1 ;;
      ok)                 printf 'Getting User settings...\nAccount Name: digithings\nAccount ID: abc123\nScopes: workers:write\nAPI Token: ***\n'; exit 0 ;;
      *)                  printf 'unknown STUB_AUTH=%s\n' "$STUB_AUTH" >&2; exit 98 ;;
    esac ;;
  *"secret list"*)
    case "$STUB_SECRETS" in
      present) printf '%s' "$STUB_LIST_WITH" ; exit 0 ;;
      absent)  printf '%s' "$STUB_LIST_WITHOUT" ; exit 0 ;;
      unreadable) printf '%s' "$STUB_EXPIRED" ; exit 1 ;;
      *)       printf 'unknown STUB_SECRETS=%s\n' "$STUB_SECRETS" >&2; exit 98 ;;
    esac ;;
  *"secret list"*) : ;;
esac
# Refuse to emulate any state change, loudly.
for m in 'deploy' 'secret put' 'secret delete' 'versions' 'publish'; do
  case "$args" in
    *"$m"*) printf 'STUB REFUSED a mutating wrangler call: %s\n' "$args" >&2; exit 97 ;;
  esac
done
printf 'STUB received unexpected wrangler call: %s\n' "$args" >&2
exit 96
"""


def run_scenario(name, auth, secrets, expect_fail, expect_absent=(), expect_present=()):
    with tempfile.TemporaryDirectory() as td:
        td = Path(td)
        stub = td / "npx"
        stub.write_text(NPX_STUB)
        stub.chmod(0o755)
        log = td / "calls.log"

        env = dict(os.environ)
        env.update(
            PATH=f"{td}:{env['PATH']}",
            WRANGLER_CALL_LOG=str(log),
            STUB_AUTH=auth,
            STUB_SECRETS=secrets,
            STUB_EXPIRED=EXPIRED_TOKEN,
            STUB_NOTAUTH=NOT_AUTHENTICATED,
            STUB_BADTOKEN=LOGGED_IN,
            STUB_LIST_WITH=SECRET_LIST_WITH,
            STUB_LIST_WITHOUT=SECRET_LIST_WITHOUT,
        )
        # An interactive login must win over any ambient token, so make sure the
        # stub is reached for the same reason it is reached in production.
        env.pop("CLOUDFLARE_API_TOKEN", None)
        env.pop("CLOUDFLARE_ACCOUNT_ID", None)

        proc = subprocess.run(
            ["bash", str(ROLLOUT)],
            cwd=REPO_ROOT,
            env=env,
            stdin=subprocess.DEVNULL,  # no interactive input: never block
            capture_output=True,
            text=True,
            timeout=120,
        )
        calls = log.read_text() if log.exists() else ""
        out = proc.stdout + proc.stderr
        failures = []

        if expect_fail and proc.returncode == 0:
            failures.append("expected a non-zero exit, got 0")
        if not expect_fail and proc.returncode != 0:
            failures.append(f"expected preflight to pass, exit={proc.returncode}")
        for needle in expect_present:
            if needle not in out:
                failures.append(f"missing expected output: {needle!r}")
        for needle in expect_absent:
            if needle in out:
                failures.append(f"forbidden output present: {needle!r}")
        for m in MUTATING:
            if m in calls:
                failures.append(f"reached a mutating wrangler call ({m!r}) before refusing")
        if "STUB REFUSED" in out or "STUB received unexpected" in out:
            failures.append("stub intercepted a call the guard should have prevented")

        if failures:
            print(f"FAIL  {name}", file=sys.stderr)
            for f in failures:
                print(f"        - {f}", file=sys.stderr)
            print(f"        exit={proc.returncode}", file=sys.stderr)
            print("        wrangler calls:", file=sys.stderr)
            for line in calls.splitlines() or ["(none)"]:
                print(f"          {line}", file=sys.stderr)
            print("        --- script output (tail) ---", file=sys.stderr)
            for line in out.strip().splitlines()[-14:]:
                print(f"          {line}", file=sys.stderr)
            return False
        print(f"ok    {name}")
        return True


def main():
    if not ROLLOUT.exists():
        print(f"FAIL  rollout script not found: {ROLLOUT}", file=sys.stderr)
        return 1

    results = [
        # The regression. An expired token must be refused as an auth problem and
        # must never be reported as a missing secret.
        run_scenario(
            "expired token is refused as auth, not reported as missing secret",
            auth="expired",
            secrets="unreadable",
            expect_fail=True,
            expect_present=["FATAL", "not authenticated"],
            expect_absent=[
                "is not set on this Worker",
                "could not confirm a Cloudflare identity",
            ],
        ),
        run_scenario(
            "'You are not authenticated' is refused as auth",
            auth="not_authenticated",
            secrets="unreadable",
            expect_fail=True,
            expect_present=["FATAL", "not authenticated"],
            expect_absent=["is not set on this Worker"],
        ),
        # A genuinely unlistable secret set must also be auth/network, not "absent".
        run_scenario(
            "unreadable secret list is not reported as an absent secret",
            auth="ok",
            secrets="unreadable",
            expect_fail=True,
            expect_present=["could not read the secret list"],
            expect_absent=["is not set on this Worker"],
        ),
        # The true "absent" verdict must survive the fix.
        run_scenario(
            "genuinely absent secret still reports the absent-secret verdict",
            auth="ok",
            secrets="absent",
            expect_fail=True,
            expect_present=["is not set on this Worker"],
            expect_absent=["could not read the secret list"],
        ),
        # And a healthy preflight must still pass, so the fix cannot wedge the rollout.
        # Reaching step 1/7 proves both preflight guards cleared. The non-zero exit
        # is correct downstream behaviour: with no input on stdin the key is empty,
        # and the script must stop rather than write an empty registry.
        run_scenario(
            "authenticated preflight clears both guards and empty input writes nothing",
            auth="ok",
            secrets="present",
            expect_fail=True,
            expect_present=[
                "0/7 preflight: confirm the secret name already exists",
                "1/7 read the new OCC invite key",
                "the new OCC invite key was empty",
            ],
            expect_absent=[
                "is not set on this Worker",
                "could not read the secret list",
                "not authenticated",
                "could not confirm a Cloudflare identity",
            ],
        ),
    ]

    if all(results):
        print("\nOK: occ rollout auth guard refuses safely on every scenario.")
        return 0
    print("\nFAILED: see above.", file=sys.stderr)
    return 1


if __name__ == "__main__":
    sys.exit(main())