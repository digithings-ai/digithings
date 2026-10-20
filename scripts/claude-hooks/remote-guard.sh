#!/usr/bin/env bash
# Block `git push` / `git remote add|set-url` to any remote that isn't the
# pinned digithings origin. Prevents accidental pushes to forks or other repos.
source "$(dirname "$0")/_lib.sh"

cmd="$(hook_field command)"
[ -z "$cmd" ] && exit 0

# Normalize whitespace.
norm="$(printf '%s' "$cmd" | tr -s '[:space:]' ' ')"

# GitHub public/release remote, the Origin mirror, and the Origin-only /local endpoint.
allowed_url_regex='^(https://github\.com/digithings-ai/digithings(\.git)?|git@github\.com:digithings-ai/digithings(\.git)?|https://origin\.cursor\.com/chrizefan/digithings(\.git)?(/local/?)?)$'

# Case: `git remote add <name> <url>` or `git remote set-url <name> <url>`
if [[ "$norm" =~ git[[:space:]]+remote[[:space:]]+(add|set-url)[[:space:]]+([^[:space:]]+)[[:space:]]+([^[:space:]]+) ]]; then
  url="${BASH_REMATCH[3]}"
  if ! [[ "$url" =~ $allowed_url_regex ]]; then
    deny "refusing to add/set remote pointing at '$url'. \
Allowed: github.com/digithings-ai/digithings, or origin.cursor.com/chrizefan/digithings (and its /local endpoint)."
  fi
fi

# Case: `git push <remote> …` where <remote> may be a URL.
if [[ "$norm" =~ git[[:space:]]+push[[:space:]]+([^[:space:]]+) ]]; then
  target="${BASH_REMATCH[1]}"
  # If it looks like a URL, enforce the allowlist directly.
  if [[ "$target" == http*://* || "$target" == git@* ]]; then
    if ! [[ "$target" =~ $allowed_url_regex ]]; then
      deny "refusing to push to URL '$target'. Use 'origin' only."
    fi
  elif [ "$target" != "origin" ] && [ "$target" != "--help" ] && [ "$target" != "-h" ]; then
    # Named remote other than origin — resolve its URL via git config.
    remote_url="$(git -C "$PROJECT_ROOT" remote get-url "$target" 2>/dev/null || true)"
    if [ -n "$remote_url" ] && ! [[ "$remote_url" =~ $allowed_url_regex ]]; then
      deny "refusing to push to remote '$target' → '$remote_url'. Use 'origin' only."
    fi
  fi
fi

exit 0
