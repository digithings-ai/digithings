#!/usr/bin/env python3
"""Read-only: who created the DROP issues and what does the parent look like?"""
import json, os, urllib.request, sys

BASE = "http://127.0.0.1:3100/api"
KEY = os.environ.get("PAPERCLIP_API_KEY")
CO = os.environ.get("PAPERCLIP_COMPANY_ID", "3d7a91f3-c674-4a9e-862b-11b9698f6686")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

identifiers = sys.argv[1:]
by_ident = {}
offset = 0
while True:
    page = get(f"/companies/{CO}/issues?limit=500&offset={offset}")
    items = page if isinstance(page, list) else (page.get("issues") or [])
    if not items:
        break
    for it in items:
        by_ident[it.get("identifier")] = it
    if len(items) < 500:
        break
    offset += 500

for ident in identifiers:
    r = by_ident.get(ident)
    if not r:
        print(ident, "NOT FOUND")
        continue
    full = get(f"/issues/{r['id']}")
    pid = full.get("parentId")
    parent = get(f"/issues/{pid}") if pid else None
    print(json.dumps({
        "identifier": ident,
        "id": full.get("id"),
        "createdByAgentId": full.get("createdByAgentId"),
        "authorType": full.get("authorType"),
        "createdAt": full.get("createdAt"),
        "updatedAt": full.get("updatedAt"),
        "pref": full.get("executionWorkspacePreference"),
        "mode": (full.get("executionWorkspaceSettings") or {}).get("mode"),
        "ws": full.get("executionWorkspaceId"),
        "assignee": full.get("assigneeAgentId"),
        "parent": (parent or {}).get("identifier"),
        "parent_pref": (parent or {}).get("executionWorkspacePreference"),
        "parent_mode": ((parent or {}).get("executionWorkspaceSettings") or {}).get("mode"),
        "parent_ws": (parent or {}).get("executionWorkspaceId"),
        "parent_creator": (parent or {}).get("createdByAgentId"),
    }))
