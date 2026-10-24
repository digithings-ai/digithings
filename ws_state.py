#!/usr/bin/env python3
import json, os, urllib.request

BASE = "http://127.0.0.1:3100/api"
KEY = os.environ.get("PAPERCLIP_API_KEY")
CO = os.environ.get("PAPERCLIP_COMPANY_ID", "3d7a91f3-c674-4a9e-862b-11b9698f6686")
ME = "38045bd4-eed9-4c4d-bbf5-bdb6b0261407"

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

# my in_progress issues
rows = []
offset = 0
while True:
    page = get(f"/companies/{CO}/issues?limit=500&offset={offset}")
    items = page if isinstance(page, list) else (page.get("issues") or [])
    if not items:
        break
    rows.extend(items)
    if len(items) < 500:
        break
    offset += 500
mine = [r for r in rows if r.get("assigneeAgentId") == ME and r.get("status") == "in_progress"]
print("my in_progress:", [(r.get("identifier"), r.get("title", "")[:60]) for r in mine])

ids = [r.get("identifier") for r in rows if r.get("projectId") == "0ae7b608-bbc7-4cfa-9a4e-297b124b49ed"]
want = ["DIG-4840", "DIG-4827", "DIG-4809", "DIG-4808", "DIG-4807", "DIG-4806", "DIG-4805", "DIG-4804", "DIG-4803", "DIG-4796", "DIG-4795"]
by_id = {r.get("identifier"): r.get("id") for r in rows}
for w in want:
    iid = by_id.get(w)
    if not iid:
        print(w, "not found")
        continue
    full = get(f"/issues/{iid}")
    s = full.get("executionWorkspaceSettings") or {}
    print(w, "pref=", full.get("executionWorkspacePreference"), "ws=", full.get("executionWorkspaceId"), "mode=", s.get("mode"))
