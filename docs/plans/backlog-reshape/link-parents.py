#!/usr/bin/env python3
"""Link child issues to their parent epic via GitHub's native sub-issue API.

Idempotent: skips any link that already exists.

Usage:
  python3 link-parents.py           # dry run
  python3 link-parents.py --apply
"""
import json, subprocess, sys

REPO_OWNER = "digithings-ai"
REPO_NAME = "digithings"

# parent-epic-number → list of child-issue-numbers
LINKS = {
    # Atlas daily-update
    295: [149, 298, 302, 303, 304],
    # Atlas profiling
    296: [305, 306, 307, 308, 309, 310, 311, 312, 313],
    # Atlas migration into digiquant
    297: [300, 314, 315, 316, 317, 318, 319, 320],
    # Website live demos
    174: [266, 261, 200, 204, 299, 301],
    # DigiClaw (reduced scope)
    173: [216, 217, 218, 220, 221],
    # DigiKey SSO federation
    175: [206, 207, 208, 209, 210, 211],
    # DigiLink
    171: [191, 192, 193, 194],
    # DigiStore
    172: [195],
    # Legacy DigiChat ecosystem epic
    8: [201, 202, 203, 205],  # #204 routed to #174 instead
    # Legacy digiquant.io epic
    9: [183],
}


def sh(cmd, check=True):
    r = subprocess.run(cmd, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise RuntimeError(f"cmd failed: {' '.join(cmd)}\n{r.stderr}")
    return r


def fetch_issue(num: int) -> dict:
    q = f"""
query {{ repository(owner: "{REPO_OWNER}", name: "{REPO_NAME}") {{
  issue(number: {num}) {{
    id number title
    subIssues(first: 50) {{ nodes {{ number }} }}
  }}
}} }}
"""
    r = sh(["gh", "api", "graphql", "-f", f"query={q}"])
    return json.loads(r.stdout)["data"]["repository"]["issue"]


def add_subissue(parent_id: str, child_id: str):
    q = ("mutation($p:ID!,$c:ID!){addSubIssue(input:{issueId:$p,subIssueId:$c})"
         "{issue{id}}}")
    sh(["gh", "api", "graphql", "-f", f"query={q}",
        "-f", f"p={parent_id}", "-f", f"c={child_id}"])


def main():
    apply = "--apply" in sys.argv
    print(("APPLY" if apply else "DRY RUN") + "\n")

    # Cache for issue node IDs
    cache: dict[int, dict] = {}

    def get(num):
        if num not in cache:
            cache[num] = fetch_issue(num)
        return cache[num]

    linked, skipped, failed = 0, 0, 0
    for parent_n, children in LINKS.items():
        parent = get(parent_n)
        existing = {n["number"] for n in parent["subIssues"]["nodes"]}
        for child_n in children:
            if child_n in existing:
                skipped += 1
                continue
            child = get(child_n)
            print(f"link #{parent_n} → #{child_n} ({child['title'][:60]})")
            if apply:
                try:
                    add_subissue(parent["id"], child["id"])
                    linked += 1
                except RuntimeError as e:
                    print(f"  FAIL: {e}")
                    failed += 1
            else:
                linked += 1

    print(f"\nSummary: linked={linked} skipped={skipped} failed={failed}")


if __name__ == "__main__":
    main()
