#!/usr/bin/env python3
"""Post the third DIG-4841 comment and read it back."""
import json
import os
import urllib.request

BASE = "http://127.0.0.1:3100/api"
KEY = os.environ["PAPERCLIP_API_KEY"]
ISSUE = "fcc173ef-8201-4089-a2fe-043c1fbdea53"
HERE = os.path.dirname(os.path.abspath(__file__))


def call(method, path, payload=None):
    data = None if payload is None else json.dumps(payload).encode()
    req = urllib.request.Request(
        BASE + path,
        data=data,
        method=method,
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode()


with open(os.path.join(HERE, "comment3.md")) as fh:
    comment = fh.read()

status, body = call("POST", "/issues/%s/comments" % ISSUE, {"body": comment})
print("comment", status, body[:300])

status, body = call("GET", "/issues/%s/comments" % ISSUE)
comments = json.loads(body)
items = comments if isinstance(comments, list) else (comments.get("comments") or [])
last = items[-1] if items else {}
print(
    "readback",
    status,
    "count",
    len(items),
    "| id",
    last.get("id"),
    "| authorType",
    last.get("authorType"),
    "| authorAgentId",
    last.get("authorAgentId"),
    "| body_head",
    (last.get("body") or "")[:60],
)
