#!/usr/bin/env python3
"""Repair the DROP class: issues with a resolved mode but an empty preference.

Only unbound issues are repaired here. A bound issue keeps its binding; its
preference is healed by the platform write-back once the fix ships.
"""
import json, os, sys, urllib.request

BASE = "http://127.0.0.1:3100/api"
KEY = os.environ.get("PAPERCLIP_API_KEY")
CO = os.environ.get("PAPERCLIP_COMPANY_ID", "3d7a91f3-c674-4a9e-862b-11b9698f6686")
MAX_ISSUES = 20

if not KEY:
    sys.exit("no PAPERCLIP_API_KEY")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

def patch(path, body):
    data = json.dumps(body).encode()
    req = urllib.request.Request(
        BASE + path, data=data, method="PATCH",
        headers={"Authorization": "Bearer " + KEY, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

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

dig = [r for r in rows if r.get("projectId") == "0ae7b608-bbc7-4cfa-9a4e-297b124b49ed"]
dig.sort(key=lambda r: r.get("createdAt") or "", reverse=True)

targets = []
for r in dig:
    if len(targets) >= MAX_ISSUES:
        break
    full = get(f"/issues/{r['id']}")
    pref = full.get("executionWorkspacePreference")
    ws = full.get("executionWorkspaceId")
    settings = full.get("executionWorkspaceSettings") or {}
    mode = settings.get("mode")
    if full.get("status") == "in_progress":
        # A running agent owns the issue; do not race its writes.
        continue
    if pref is None and ws is None and mode in ("isolated_workspace", "operator_branch", "shared_workspace"):
        targets.append((full.get("identifier"), full["id"], mode))

receipt = []
for ident, iid, mode in targets:
    want = mode
    try:
        patch(f"/issues/{iid}", {"executionWorkspacePreference": want})
    except Exception as e:
        receipt.append({"issue": ident, "result": f"PATCH failed: {e}"})
        continue
    back = get(f"/issues/{iid}")
    pref = back.get("executionWorkspacePreference")
    ws = back.get("executionWorkspaceId")
    mode_back = (back.get("executionWorkspaceSettings") or {}).get("mode")
    ok = pref == want and ws is None and mode_back == mode
    receipt.append({
        "issue": ident, "pref": pref, "ws": ws, "mode": mode_back,
        "result": "OK" if ok else "MISMATCH",
    })

print(json.dumps(receipt, indent=1))
print("repaired:", sum(1 for r in receipt if r.get("result") == "OK"), "of", len(receipt))
