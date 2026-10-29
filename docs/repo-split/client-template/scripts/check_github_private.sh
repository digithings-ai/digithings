#!/usr/bin/env bash
# Refuse unless this repo's `github` backup remote is an EXISTING, PRIVATE repo owned by
# GITHUB_OWNER. Fails closed: no `github` remote, a URL that is not github.com/<owner>/<name>,
# the wrong owner, no `gh`, a gh error (including 404: the repo must already exist, so the
# owner's first push can never create one), or any answer other than exactly `true` refuses.
#
# Env:
#   GITHUB_OWNER  required; the only owner the backup may live under. Set once in the
#                 Makefile (GITHUB_OWNER ?= digithings-ai); unset or empty refuses.
set -euo pipefail
refuse() { echo "refused: $*" >&2; exit 1; }

want="${GITHUB_OWNER:-}"
[ -n "$want" ] || refuse "GITHUB_OWNER is not set (the Makefile sets it)"

url="$(git remote get-url github 2>/dev/null)" || refuse "no git remote 'github' (add the private backup first)"
url="${url%/}"
# https://[user@]github.com/owner/name[.git] | git@github.com:owner/name[.git] | ssh://git@github.com/owner/name[.git]
part='[A-Za-z0-9._-]+'
if [[ "$url" =~ ^https://([^@/]+@)?github\.com/($part)/($part)$ ]]; then
  owner="${BASH_REMATCH[2]}"; name="${BASH_REMATCH[3]}"
elif [[ "$url" =~ ^(ssh://)?git@github\.com[:/]($part)/($part)$ ]]; then
  owner="${BASH_REMATCH[2]}"; name="${BASH_REMATCH[3]}"
else
  refuse "github remote is not a github.com/<owner>/<name> URL"
fi
name="${name%.git}"
[ -n "$name" ] && [ "$name" != . ] && [ "$name" != .. ] || refuse "github remote has no repo name"
[ "$owner" = "$want" ] || refuse "github remote owner '$owner' is not GITHUB_OWNER '$want'"

command -v gh >/dev/null 2>&1 || refuse "no 'gh' CLI to read the GitHub repo's private flag"
flag="$(GH_PROMPT_DISABLED=1 gh api "repos/$owner/$name" --jq .private 2>/dev/null)" \
  || refuse "could not read $owner/$name from the GitHub API (missing repo, no access, or gh error)"
[ "$flag" = "true" ] || refuse "GitHub repo $owner/$name is not private (private flag: '${flag:0:40}')"
echo "ok: GitHub repo $owner/$name is private"
