#!/usr/bin/env bash
# Verify the current Forgejo branch-protection matrix (localhost:3000).
#
# The matrix is the one documented in docs/ops/forgejo-branch-protection.md.
# It is deliberately not uniform: main is strict, the integration branch is
# lighter. A missing rule is a failure, not a crash.
#
# The inventory (which repo, which branch, which profile) is NOT in this file:
# some of those repos carry a client name, and this tree is public (the R0
# client-literals guard). It comes from FORGEJO_PROTECTED_REPOS in the local
# forge env file as a comma-separated list of `repo:branch:profile`, where the
# profile is `strict`, `light`, `strict-signed` or `light-signed`. The two
# `-signed` profiles are `strict` and `light` with `require_signed_commits`
# expected true, for branches switched to signed commits; `strict` and `light`
# stay as they were (signed false) for the exempt mirrored branches. An unset or
# empty inventory is a failure, not an empty pass: a verifier that checks
# nothing must not report OK.
#
# The token is never an argument: this script exports it and the Python reads
# os.environ["FORGEJO_TOKEN"], so no token value reaches process argv.
set -euo pipefail

ENV_FILE="${LOCAL_FORGE_ENV:-$HOME/Code/source-control/deploy/local-forge/local-forge.env}"
if [ ! -f "$ENV_FILE" ]; then
  echo "branch-protection-verify: env file not found: $ENV_FILE" >&2
  echo "Set LOCAL_FORGE_ENV to the Forgejo env file." >&2
  exit 1
fi
# The env file is local and never committed, so shellcheck cannot follow it.
set -a
# shellcheck source=/dev/null
. "$ENV_FILE"
set +a

BASE="${FORGEJO_URL:-http://localhost:3000}"
OWNER="${FORGEJO_REPO_ORG:-digithings-ai}"

if [ -z "${FORGEJO_TOKEN:-}" ]; then
  echo "branch-protection-verify: FORGEJO_TOKEN is unset in $ENV_FILE" >&2
  exit 1
fi
if [ -z "${FORGEJO_PROTECTED_REPOS:-}" ]; then
  echo "branch-protection-verify: FORGEJO_PROTECTED_REPOS is unset in $ENV_FILE" >&2
  echo "Set it to a comma-separated repo:branch:profile list; see" >&2
  echo "docs/ops/forgejo-branch-protection.md for the format." >&2
  exit 1
fi

python3 - "$BASE" "$OWNER" <<'PY'
import json
import os
import sys
import urllib.error
import urllib.request

base, owner = sys.argv[1:3]
token = os.environ["FORGEJO_TOKEN"]
headers = {"Authorization": "token " + token}

FIELDS = (
    "enable_push",
    "required_approvals",
    "enable_status_check",
    "require_signed_commits",
    "apply_to_admins",
    "block_on_rejected_reviews",
    "dismiss_stale_approvals",
    "block_on_outdated_branch",
)

# The two documented base profiles, in FIELDS order. The repo/branch pairs they
# apply to live in FORGEJO_PROTECTED_REPOS (local env file), not here.
BASE_PROFILES = {
    "strict": (False, 1, True, False, True, True, True, True),
    "light": (False, 1, False, False, True, True, False, False),
}
SIGNED = FIELDS.index("require_signed_commits")


def signed(profile: tuple) -> tuple:
    """The same profile with require_signed_commits expected true."""
    return profile[:SIGNED] + (True,) + profile[SIGNED + 1 :]


# `strict`/`light` are unchanged (signed false: the exempt mirrored branches).
# `strict-signed`/`light-signed` differ from them in the signed field only.
PROFILES = {
    **BASE_PROFILES,
    **{f"{name}-signed": signed(values) for name, values in BASE_PROFILES.items()},
}


def inventory() -> list[tuple[str, str, str]]:
    """The repo:branch:profile triples from the local env file."""
    rows = []
    for item in os.environ["FORGEJO_PROTECTED_REPOS"].split(","):
        item = item.strip()
        if not item:
            continue
        fields = item.split(":")
        if len(fields) != 3:
            raise SystemExit(
                f"FORGEJO_PROTECTED_REPOS: '{item}' is not repo:branch:profile"
            )
        repo, branch, profile = fields
        if profile not in PROFILES:
            raise SystemExit(
                f"FORGEJO_PROTECTED_REPOS: '{item}' names unknown profile '{profile}'"
            )
        rows.append((repo, branch, profile))
    if not rows:
        raise SystemExit("FORGEJO_PROTECTED_REPOS lists no rules to verify")
    return rows


MATRIX = inventory()

rules: dict[tuple[str, str], dict] = {}
failures = 0
for repo in sorted({row[0] for row in MATRIX}):
    url = f"{base}/api/v1/repos/{owner}/{repo}/branch_protections"
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as response:
            data = json.load(response)
    except urllib.error.HTTPError as exc:
        print(f"MISSING {repo}: cannot read protections (HTTP {exc.code})")
        failures += 1
        continue
    except Exception as exc:  # noqa: BLE001 - report, do not crash
        print(f"MISSING {repo}: cannot read protections ({exc})")
        failures += 1
        continue
    for rule in data:
        rules[(repo, rule["rule_name"])] = rule

gaps = 0
for repo, branch, profile in MATRIX:
    rule = rules.get((repo, branch))
    if rule is None:
        print(f"MISSING {repo}/{branch}: no protection rule")
        failures += 1
        continue
    for field, want in zip(FIELDS, PROFILES[profile]):
        got = rule.get(field)
        if got != want:
            print(f"MISMATCH {repo}/{branch}: {field} = {got!r} (expected {want!r})")
            failures += 1
    if rule.get("enable_status_check") and not rule.get("status_check_contexts"):
        gaps += 1
        print(f"GAP {repo}/{branch}: status checks enabled with no required context")

if failures:
    print(f"branch protection verification FAILED ({failures} mismatch(es))")
    raise SystemExit(1)

repos = len({row[0] for row in MATRIX})
print(f"branch protection verification OK ({len(MATRIX)} rules across {repos} repos)")
if gaps:
    print(
        f"current state, not the target: {gaps} rule(s) enable status checks and "
        "name no required context (the GAP lines above)"
    )
print("Known gaps are documented in docs/ops/forgejo-branch-protection.md")
PY
