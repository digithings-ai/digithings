"""Read-only Woodpecker API helper for this run.

Reads the deployment's own token from the local-forge env file and prints
API answers only. No secret value is ever printed.
"""

import json
import os
import sys
import urllib.error
import urllib.request

ENV = os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..",
    "..",
    "..",
    "..",
    "..",
    "Code",
    "source-control",
    "deploy",
    "local-forge",
    "local-forge.env",
)


def envfile(path):
    out = {}
    with open(path, encoding="utf-8", errors="replace") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, _, value = line.partition("=")
            out[key.strip().removeprefix("export ").strip()] = value.strip().strip("'\"")
    return out


def base_url(env):
    base = env.get("WOODPECKER_URL", "http://127.0.0.1").rstrip("/").rstrip(":")
    port = env.get("WOODPECKER_HTTP_PORT", "")
    if port and ":" + port not in base:
        base = base + ":" + port
    return base


def api(env, path, raw=False):
    req = urllib.request.Request(
        base_url(env) + path,
        headers={"Authorization": "Bearer " + env.get("WOODPECKER_TOKEN", "")},
    )
    try:
        with urllib.request.urlopen(req, timeout=25) as resp:
            body = resp.read().decode("utf-8", "replace")
            return body if raw else json.loads(body or "null")
    except urllib.error.HTTPError as exc:
        return {"_http": exc.code, "_body": exc.read()[:400].decode("utf-8", "replace")}


if __name__ == "__main__":
    env = envfile(os.path.expanduser(sys.argv[1] if len(sys.argv) > 1 else ENV))
    print(base_url(env))
    print(json.dumps(api(env, sys.argv[2], raw="--raw" in sys.argv), indent=2)[:4000])
