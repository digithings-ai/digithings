#!/usr/bin/env python3
"""Post the DIG-4841 follow-up comment and update the unblock descriptor."""
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
        BASE + path, data=data, method=method,
        headers={
            "Authorization": "Bearer " + KEY,
            "Content-Type": "application/json",
        },
    )
    with urllib.request.urlopen(req) as resp:
        return resp.status, resp.read().decode()


status, body = call("GET", "/issues/%s/interactions" % ISSUE)
print("interactions", status, body[:800])

with open(os.path.join(HERE, "comment2.md")) as fh:
    comment = fh.read()

status, body = call("POST", "/issues/%s/comments" % ISSUE, {"body": comment})
print("comment", status, body[:400])

status, body = call(
    "PATCH",
    "/issues/%s" % ISSUE,
    {
        "unblockDescriptor": {
            "owner": {"agentId": "38045bd4-eed9-4c4d-bbf5-bdb6b0261407"},
            "action": (
                "Chris reviews and merges digithings-ai/paperclip#51 (the fork's pull request CI "
                "never starts, so the local verification receipt in the PR body is the gate), then "
                "Chris restarts Paperclip. After the restart the write-back keeps the isolated "
                "preference, the 117 bound issues heal on their next run, and the remaining 37 "
                "DROP issues are the last repair batch for the sweep."
            ),
        }
    },
)
print("patch", status, body[:300])

status, body = call("GET", "/issues/%s" % ISSUE)
d = json.loads(body)
print("read-back status:", d.get("status"))
print("unblock:", json.dumps(d.get("unblockDescriptor")))
