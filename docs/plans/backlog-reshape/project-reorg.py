#!/usr/bin/env python3
"""Reorganize projects per parent/child delegation model.

Rules:
- Project #1 (digithings) = ROOT: epics + cross-cutting tasks only.
- Projects #2..#9 (module projects) = module-scoped issues.
- Project #10 (sitaas) = SITAAS items.
- Project #11 (maintenance) = tooling/CI/housekeeping (component:root + type:infra, non-epic).

Operations per open issue:
- Compute target project set.
- Add to missing targets; remove from projects no longer desired.
- On each target project: set Priority + Kind + Status (Status only if None; never downgrades In Progress).

Idempotent — re-run safely.

Usage:
  python3 project-reorg.py             # dry run
  python3 project-reorg.py --apply     # execute
"""
from __future__ import annotations
import json
import subprocess
import sys

REPO = "digithings-ai/digithings"
OWNER = "digithings-ai"

# Project IDs + field + option maps
PROJECTS = {
    1:  {"pid": "PVT_kwDODCLeec4BVAGj",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVAGjzhQe7J8",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Review": "e2a96a83", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVAGjzhQe7Vs",
                          "opts": {"P0": "0efbf390", "P1": "cc02d53a", "P2": "fc431d36", "P3": "c4bda5c6"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVAGjzhQe7bc",
                          "opts": {"Epic": "460e6ce9", "Feature": "83196803", "Task": "bca36774",
                                   "Bug": "d57c41ef", "Chore": "76193410", "Research": "40c40521"}},
         }},
    2:  {"pid": "PVT_kwDODCLeec4BVEv8",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVEv8zhQjA1A",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVEv8zhQjA7k",
                          "opts": {"P0": "196d8748", "P1": "79c72f52", "P2": "4bfa277e", "P3": "db4aced7"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVEv8zhQjA6s",
                          "opts": {"Epic": "670a91c5", "Feature": "a4facc97", "Task": "00bb0377",
                                   "Bug": "b4538014", "Chore": "80e6c501", "Research": "28a64754"}},
         }},
    3:  {"pid": "PVT_kwDODCLeec4BVFX5",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFX5zhQjj04",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFX5zhQjj2s",
                          "opts": {"P0": "93b37828", "P1": "363e25c7", "P2": "4610ede4", "P3": "6b5607c3"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFX5zhQjj2o",
                          "opts": {"Epic": "81afb922", "Feature": "76729bcf", "Task": "ff835632",
                                   "Bug": "d1f40026", "Chore": "27a22bc0", "Research": "749bd970"}},
         }},
    4:  {"pid": "PVT_kwDODCLeec4BVFX8",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFX8zhQjj3w",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFX8zhQjj6M",
                          "opts": {"P0": "b3312d60", "P1": "d5ef542a", "P2": "f5902460", "P3": "4110a9eb"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFX8zhQjj50",
                          "opts": {"Epic": "9b3cfd7b", "Feature": "8d3bf9d0", "Task": "7fb77245",
                                   "Bug": "8095d23d", "Chore": "ae5b6943", "Research": "1acb109f"}},
         }},
    5:  {"pid": "PVT_kwDODCLeec4BVFX_",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFX_zhQjj7o",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFX_zhQjj_g",
                          "opts": {"P0": "52738205", "P1": "0a5efbfa", "P2": "5d95ed88", "P3": "233284c0"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFX_zhQjj9U",
                          "opts": {"Epic": "dfc9ddde", "Feature": "211a59da", "Task": "3bfe0a07",
                                   "Bug": "7152efd9", "Chore": "448a0ad2", "Research": "acc16005"}},
         }},
    6:  {"pid": "PVT_kwDODCLeec4BVFYE",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFYEzhQjkAs",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFYEzhQjkCk",
                          "opts": {"P0": "472bb1ad", "P1": "e4b3fb3b", "P2": "d0c63875", "P3": "4450bd45"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFYEzhQjkCY",
                          "opts": {"Epic": "56aadc4c", "Feature": "d6a8f6e9", "Task": "42dd70c4",
                                   "Bug": "67702919", "Chore": "338f0d2b", "Research": "2986ad96"}},
         }},
    7:  {"pid": "PVT_kwDODCLeec4BVFYG",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFYGzhQjkC0",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFYGzhQjkHg",
                          "opts": {"P0": "e46da589", "P1": "033a3211", "P2": "3e4205a0", "P3": "829cd18b"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFYGzhQjkG8",
                          "opts": {"Epic": "3d90949e", "Feature": "35599f54", "Task": "733bb176",
                                   "Bug": "31ce8163", "Chore": "98e92ab3", "Research": "277d236c"}},
         }},
    8:  {"pid": "PVT_kwDODCLeec4BVFYM",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFYMzhQjkIY",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFYMzhQjkJU",
                          "opts": {"P0": "c981dd23", "P1": "aa5a7664", "P2": "83d8e78c", "P3": "e9bef587"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFYMzhQjkJQ",
                          "opts": {"Epic": "f51a8c32", "Feature": "907f8b50", "Task": "e3c6c0a3",
                                   "Bug": "54e03cd7", "Chore": "91187d05", "Research": "110673db"}},
         }},
    9:  {"pid": "PVT_kwDODCLeec4BVFYR",
         "fields": {
             "Status":   {"id": "PVTSSF_lADODCLeec4BVFYRzhQjkM0",
                          "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
             "Priority": {"id": "PVTSSF_lADODCLeec4BVFYRzhQjkNw",
                          "opts": {"P0": "17f99a6b", "P1": "40786aab", "P2": "b477f563", "P3": "0b032332"}},
             "Kind":     {"id": "PVTSSF_lADODCLeec4BVFYRzhQjkNs",
                          "opts": {"Epic": "82718330", "Feature": "76ea968c", "Task": "0c9d0eb1",
                                   "Bug": "f09ea540", "Chore": "458b94cf", "Research": "52f9af12"}},
         }},
    10: {"pid": "PVT_kwDODCLeec4BVFpK",
         "fields": {
             "Status": {"id": "PVTSSF_lADODCLeec4BVFpKzhQjzMs",
                        "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
         }},
    11: {"pid": "PVT_kwDODCLeec4BVGBo",
         "fields": {
             "Status": {"id": "PVTSSF_lADODCLeec4BVGBozhQkI2E",
                        "opts": {"Todo": "f75ad846", "In Progress": "47fc9ee4", "Done": "98236657"}},
         }},
}

COMPONENT_TO_PROJECT = {
    "component:digiquant":  2,
    "component:digigraph":  3,
    "component:digisearch": 4,
    "component:digichat":   5,
    "component:digikey":    6,
    "component:digismith":  7,
    "component:digiclaw":   8,
    "component:digibase":   9,
}
PRIO_FROM_LABEL = {"priority:critical": "P0", "priority:high": "P1",
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


def fetch_project_items(n):
    r = sh(["gh", "project", "item-list", str(n), "--owner", OWNER,
            "--limit", "300", "--format", "json"])
    out = {}
    for it in json.loads(r.stdout)["items"]:
        c = it.get("content") or {}
        num = c.get("number")
        if num is None:
            continue
        out[num] = {
            "itemId": it["id"],
            "status": it.get("status"),
            "priority": it.get("priority"),
            "kind": it.get("kind"),
        }
    return out


def add_to_project(pid, content_id):
    q = ('mutation($p:ID!,$c:ID!){addProjectV2ItemById(input:{projectId:$p,contentId:$c})'
         '{item{id}}}')
    r = sh(["gh", "api", "graphql", "-f", f"query={q}",
            "-f", f"p={pid}", "-f", f"c={content_id}"])
    return json.loads(r.stdout)["data"]["addProjectV2ItemById"]["item"]["id"]


def remove_from_project(pid, item_id):
    q = ('mutation($p:ID!,$i:ID!){deleteProjectV2Item(input:{projectId:$p,itemId:$i})'
         '{deletedItemId}}')
    sh(["gh", "api", "graphql", "-f", f"query={q}",
        "-f", f"p={pid}", "-f", f"i={item_id}"])


def set_field(pid, item_id, field_id, opt_id):
    q = ('mutation($p:ID!,$i:ID!,$f:ID!,$o:String!){'
         'updateProjectV2ItemFieldValue(input:{projectId:$p,itemId:$i,fieldId:$f,'
         'value:{singleSelectOptionId:$o}}){projectV2Item{id}}}')
    sh(["gh", "api", "graphql", "-f", f"query={q}",
        "-f", f"p={pid}", "-f", f"i={item_id}", "-f", f"f={field_id}",
        "-f", f"o={opt_id}"])


def classify(issue):
    """Return (target_projects: set[int], reason: str)."""
    ls = set(issue["l"])
    is_epic = "epic" in ls
    is_sitaas = "sitaas" in ls
    is_infra = "type:infra" in ls

    # Primary module project
    module_proj = None
    for lab, proj in COMPONENT_TO_PROJECT.items():
        if lab in ls:
            module_proj = proj
            break

    targets = set()

    if is_sitaas:
        targets.add(10)

    if is_epic:
        targets.add(1)
        # Epics ALSO appear on their module project for visibility
        if module_proj:
            targets.add(module_proj)
        return targets, "epic"

    if module_proj:
        # Module-scoped task — lives ONLY on its module project
        targets.add(module_proj)
        return targets, f"module:{module_proj}"

    # component:root (no module label)
    if is_infra:
        targets.add(11)
        return targets, "maintenance"

    targets.add(1)
    return targets, "cross-cutting"


def priority_from_labels(labels):
    ls = set(labels)
    for lab, pri in PRIO_FROM_LABEL.items():
        if lab in ls:
            return pri
    return "P2"


def kind_from_labels(labels):
    ls = set(labels)
    if "epic" in ls:
        return "Epic"
    if "type:research" in ls:
        return "Research"
    if "type:infra" in ls:
        return "Chore"
    if "type:migration" in ls:
        return "Task"
    if "type:feature" in ls:
        return "Feature"
    if "type:integration" in ls:
        return "Feature"
    return "Task"


def main():
    apply = "--apply" in sys.argv
    print(("APPLY" if apply else "DRY RUN") + "\n")

    issues = fetch_open_issues()
    print(f"Open issues: {len(issues)}")
    project_items = {n: fetch_project_items(n) for n in PROJECTS}
    for n, items in project_items.items():
        print(f"  #{n}: {len(items)} items")
    print()

    added, removed, field_updates = 0, 0, 0
    for i in issues:
        targets, reason = classify(i)
        actual = {n for n in PROJECTS if i["n"] in project_items[n]}
        to_add = targets - actual
        to_remove = actual - targets

        if to_add or to_remove:
            print(f"#{i['n']} [{reason}] {i['t'][:60]}")
            for n in sorted(to_add):
                print(f"  + add to #{n}")
            for n in sorted(to_remove):
                print(f"  - remove from #{n}")

        # Execute adds
        for n in to_add:
            if apply:
                new_item_id = add_to_project(PROJECTS[n]["pid"], i["id"])
                project_items[n][i["n"]] = {"itemId": new_item_id,
                                             "status": None, "priority": None, "kind": None}
            added += 1

        # Execute removes
        for n in to_remove:
            item_id = project_items[n][i["n"]]["itemId"]
            if apply:
                remove_from_project(PROJECTS[n]["pid"], item_id)
            del project_items[n][i["n"]]
            removed += 1

        # Refresh fields on all target projects
        desired_priority = priority_from_labels(i["l"])
        desired_kind = kind_from_labels(i["l"])
        for n in targets:
            if i["n"] not in project_items[n]:
                continue  # dry-run: wasn't actually added
            item = project_items[n][i["n"]]
            proj = PROJECTS[n]
            # Priority
            if "Priority" in proj["fields"] and item.get("priority") != desired_priority:
                if apply:
                    set_field(proj["pid"], item["itemId"],
                              proj["fields"]["Priority"]["id"],
                              proj["fields"]["Priority"]["opts"][desired_priority])
                print(f"    #{n}.Priority: {item.get('priority')} → {desired_priority}")
                field_updates += 1
            # Kind
            if "Kind" in proj["fields"] and not item.get("kind"):
                if apply:
                    set_field(proj["pid"], item["itemId"],
                              proj["fields"]["Kind"]["id"],
                              proj["fields"]["Kind"]["opts"][desired_kind])
                print(f"    #{n}.Kind: None → {desired_kind}")
                field_updates += 1
            # Status: only set if None (don't downgrade In Progress to Todo)
            if "Status" in proj["fields"] and not item.get("status"):
                if apply:
                    set_field(proj["pid"], item["itemId"],
                              proj["fields"]["Status"]["id"],
                              proj["fields"]["Status"]["opts"]["Todo"])
                print(f"    #{n}.Status: None → Todo")
                field_updates += 1

    print(f"\nSummary: added={added} removed={removed} field_updates={field_updates}")


if __name__ == "__main__":
    main()
