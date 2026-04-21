#!/usr/bin/env python3
"""Backfill Project #1 for all open issues.

- Adds any open issue not on the project.
- For every item missing Phase/Area/Priority/Kind, derives from labels+title and sets.
- Idempotent: existing values are NOT overwritten.

Usage:
  python3 project-backfill.py            # dry run
  python3 project-backfill.py --apply    # execute
"""
import json
import subprocess
import sys

PROJECT_ID = "PVT_kwDODCLeec4BVAGj"
OWNER = "digithings-ai"
REPO = "digithings-ai/digithings"

FIELD = {
    "phase":    "PVTSSF_lADODCLeec4BVAGjzhQe7Rw",
    "area":     "PVTSSF_lADODCLeec4BVAGjzhQe7Vo",
    "priority": "PVTSSF_lADODCLeec4BVAGjzhQe7Vs",
    "kind":     "PVTSSF_lADODCLeec4BVAGjzhQe7bc",
}
OPT = {
    "phase": {
        "Phase 2 — Hardening": "31ed826c",
        "Phase 3 — Domain unification": "af0cc88d",
        "Phase 4 — Atlas on DigiGraph": "5c4138a8",
        "Phase 5 — Atlas tiering": "dac4d6ce",
        "Phase 6 — Platform": "1ecee05a",
        "SITAAS pilot": "cea67c2c",
    },
    "area": {
        "DigiGraph": "64fb1b51", "DigiSearch": "c4d1712a", "DigiQuant": "320e44e0",
        "DigiChat":  "f2e0930b", "DigiKey":    "87c52e14", "DigiClaw":  "2ab0471a",
        "DigiSmith": "733214e8", "DigiBase":   "67bc54a2", "Website":   "61caae04",
        "Atlas":     "e78729ab", "SITAAS":     "e911491e", "Docs":      "820a5756",
        "Infra":     "d3fbf4c4", "Cross-cutting": "70e7b58f",
    },
    "priority": {"P0": "0efbf390", "P1": "cc02d53a", "P2": "fc431d36", "P3": "c4bda5c6"},
    "kind":     {"Epic": "460e6ce9", "Feature": "83196803", "Task": "bca36774",
                 "Bug": "d57c41ef", "Chore": "76193410", "Research": "40c40521"},
}

COMPONENT_TO_AREA = {
    "component:digigraph":  "DigiGraph",
    "component:digisearch": "DigiSearch",
    "component:digiquant":  "DigiQuant",
    "component:digichat":   "DigiChat",
    "component:digikey":    "DigiKey",
    "component:digiclaw":   "DigiClaw",
    "component:digismith":  "DigiSmith",
    "component:digibase":   "DigiBase",
    "component:website":    "Website",
}
PRIO_MAP = {"priority:critical": "P0", "priority:high": "P1",
            "priority:medium": "P2", "priority:low": "P3"}


def sh(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{r.stderr}")
    return r


def fetch_open_issues():
    r = sh(["gh", "issue", "list", "--repo", REPO, "--state", "open",
            "--limit", "300", "--json", "number,title,labels,id"])
    raw = json.loads(r.stdout)
    return [{"n": i["number"], "t": i["title"], "id": i["id"],
             "l": [lab["name"] for lab in i["labels"]]} for i in raw]


def fetch_project_items():
    r = sh(["gh", "project", "item-list", "1", "--owner", OWNER,
            "--limit", "300", "--format", "json"])
    items = json.loads(r.stdout)["items"]
    out = {}
    for it in items:
        c = it.get("content") or {}
        n = c.get("number")
        if n is None:
            continue
        out[n] = {
            "itemId": it["id"],
            "phase": it.get("phase"),
            "area": it.get("area"),
            "priority": it.get("priority"),
            "kind": it.get("kind"),
        }
    return out


def add_to_project(content_id):
    q = (
        'mutation($p:ID!,$c:ID!){'
        'addProjectV2ItemById(input:{projectId:$p,contentId:$c}){item{id}}}'
    )
    r = sh(["gh", "api", "graphql", "-f", f"query={q}",
            "-f", f"p={PROJECT_ID}", "-f", f"c={content_id}"])
    return json.loads(r.stdout)["data"]["addProjectV2ItemById"]["item"]["id"]


def set_field(item_id, field_key, option_name):
    opt_id = OPT[field_key][option_name]
    fid = FIELD[field_key]
    q = (
        'mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){'
        'updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,'
        'value:{singleSelectOptionId:$o}}){projectV2Item{id}}}'
    )
    sh(["gh", "api", "graphql", "-f", f"query={q}",
        "-f", f"p={PROJECT_ID}", "-f", f"i={item_id}", "-f", f"f={fid}",
        "-f", f"o={opt_id}"])


def derive_area(labels, title):
    ls = set(labels)
    tl = title.lower()
    if "atlas" in tl or any("atlas" in l for l in labels):
        return "Atlas"
    if "sitaas" in ls or "sitaas" in tl:
        return "SITAAS"
    for comp, area in COMPONENT_TO_AREA.items():
        if comp in ls:
            return area
    if "component:root" in ls:
        if "type:infra" in ls:
            return "Infra"
        if any("website" in l for l in labels) or "website" in tl or "digithings.ai" in tl or "digiquant.io" in tl:
            return "Website"
        return "Cross-cutting"
    if "type:infra" in ls:
        return "Infra"
    return "Cross-cutting"


def derive_phase(labels, title):
    ls = set(labels)
    tl = title.lower()
    # explicit phase labels
    if "phase-3" in ls: return "Phase 3 — Domain unification"
    if "phase-4" in ls: return "Phase 4 — Atlas on DigiGraph"
    if "phase-5" in ls: return "Phase 5 — Atlas tiering"
    if "phase-2" in ls: return "Phase 2 — Hardening"
    if "sitaas"  in ls: return "SITAAS pilot"
    # Everything current is platform-phase work
    return "Phase 6 — Platform"


def derive_priority(labels):
    ls = set(labels)
    for lab, pri in PRIO_MAP.items():
        if lab in ls:
            return pri
    return "P2"


def derive_kind(labels):
    ls = set(labels)
    if "epic" in ls: return "Epic"
    if "type:research" in ls: return "Research"
    if "type:infra" in ls: return "Chore"
    if "type:migration" in ls: return "Task"
    if "type:feature" in ls: return "Feature"
    if "type:integration" in ls: return "Feature"
    return "Task"


def main():
    apply = "--apply" in sys.argv
    if not apply:
        print("DRY RUN. Pass --apply to execute.\n")

    issues = fetch_open_issues()
    project = fetch_project_items()
    print(f"Open: {len(issues)}  On project: {len(project)}")

    added = 0
    updated = 0
    skipped = 0

    for i in issues:
        n = i["n"]
        item_id = None
        if n not in project:
            if apply:
                item_id = add_to_project(i["id"])
            print(f"+ add #{n} to project: {i['t'][:70]}")
            added += 1
            existing = {"phase": None, "area": None, "priority": None, "kind": None}
        else:
            item_id = project[n]["itemId"]
            existing = project[n]

        derived = {
            "phase":    derive_phase(i["l"], i["t"]),
            "area":     derive_area(i["l"], i["t"]),
            "priority": derive_priority(i["l"]),
            "kind":     derive_kind(i["l"]),
        }
        changes = {}
        for k, v in derived.items():
            if not existing.get(k):
                changes[k] = v

        if changes:
            if apply and item_id:
                for k, v in changes.items():
                    set_field(item_id, k, v)
            print(f"  set #{n}: " + ", ".join(f"{k}={v}" for k, v in changes.items()))
            updated += 1
        else:
            skipped += 1

    print(f"\nAdded: {added}  Updated: {updated}  Already-complete: {skipped}")


if __name__ == "__main__":
    main()
