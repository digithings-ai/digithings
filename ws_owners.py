#!/usr/bin/env python3
"""Read-only: for each digithings issue, compare its bound workspace sourceIssueId with its own id."""
import json, os, urllib.request, sys

BASE = "http://127.0.0.1:3100/api"
KEY = os.environ.get("PAPERCLIP_API_KEY")
CO = os.environ.get("PAPERCLIP_COMPANY_ID", "3d7a91f3-c674-4a9e-862b-11b9698f6686")
if not KEY:
    sys.exit("no PAPERCLIP_API_KEY")

def get(path):
    req = urllib.request.Request(BASE + path, headers={"Authorization": "Bearer " + KEY})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.load(r)

rows = []
offset = 0
while True:
    page = get(f"/companies/{CO}/issues?limit=500&offset={offset}")
    items = page if isinstance(page, list) else (page.get("issues") or page.get("items") or page.get("data") or [])
    if not items:
        break
    rows.extend(items)
    if len(items) < 500:
        break
    offset += 500

dig = [r for r in rows if (r.get("projectId") == "0ae7b608-bbc7-4cfa-9a4e-297b124b49ed")]
dig.sort(key=lambda r: r.get("createdAt") or "", reverse=True)
dig = dig[:40]
print("recent digithings issues:", len(dig))

out = []
for r in dig:
    ident = r.get("identifier")
    iid = r.get("id")
    wsid = r.get("executionWorkspaceId")
    pref = r.get("executionWorkspacePreference")
    settings = r.get("executionWorkspaceSettings")
    if not settings:
        full = get(f"/issues/{iid}")
        settings = full.get("executionWorkspaceSettings")
        pref = full.get("executionWorkspacePreference", pref)
    ws = None
    if wsid:
        try:
            ws = get(f"/execution-workspaces/{wsid}")
        except Exception as e:
            ws = {"error": str(e)}
    owner = (ws or {}).get("sourceIssueId")
    out.append({
        "identifier": ident,
        "issueId": iid,
        "pref": pref,
        "mode": (settings or {}).get("mode") if isinstance(settings, dict) else settings,
        "wsId": wsid,
        "ownerIssueId": owner,
        "selfOwned": (owner == iid) if owner else None,
        "wsMode": (ws or {}).get("mode"),
        "wsStatus": (ws or {}).get("status"),
        "wsCwd": (ws or {}).get("cwd"),
        "createdAt": r.get("createdAt"),
    })

json.dump(out, open(os.path.join(os.path.dirname(os.path.abspath(__file__)), "ws_owners.json"), "w"), indent=1)

trap = [o for o in out if o["pref"] == "reuse_existing" and o["mode"] == "isolated_workspace"]
drop = [o for o in out if o["pref"] is None]
other = [o for o in trap if o["selfOwned"] is False]
print("trap-writeback:", len(trap), " drop:", len(drop), " trap bound to ANOTHER issue:", len(other))
for o in other:
    print("  CROSS-ISSUE", o["identifier"], o["wsId"], "owner", o["ownerIssueId"], o["wsCwd"])
print("--- trap detail ---")
for o in trap:
    print(" ", o["identifier"], "selfOwned=", o["selfOwned"], "wsMode=", o["wsMode"], "wsStatus=", o["wsStatus"], "cwd=", (o["wsCwd"] or "")[-60:])
print("--- drop detail ---")
for o in drop:
    print(" ", o["identifier"], "wsId=", o["wsId"], "mode=", o["mode"], "created=", o["createdAt"])
